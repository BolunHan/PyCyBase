"""Tests for SHM lifecycle cleanup (c_shm_allocator).

Contracts:
    - AP_SHM_UNLINK_ON_MAP (default 1): allocator and page SHM names are
      unlinked from /dev/shm immediately after creation; a process that
      dies without cleanup (crash / os._exit) leaks no names.
    - AP_SHM_STALE_CHECK (default 1): creating an allocator runs an
      on-start scan that unlinks stale objects (dead, zombie, or
      PID-reused creator) for the allocator's prefix and logs
      ``[AP] [STALE_SHM] ...`` to stderr.
    - dangling() / dangling_pages() / cleanup_dangling() use the same
      C-level liveness check: page names parse correctly and zombies
      count as stale.

C-level ``fprintf(stderr, ...)`` writes to fd 2, which Python-level
``redirect_stderr`` cannot capture in-process; log-content assertions
therefore run the scan in a subprocess with ``stderr=PIPE``.
"""
import ctypes
import gc
import logging
import os
import subprocess
import sys
import time
import unittest
from contextlib import suppress

_IS_LINUX = sys.platform.startswith('linux')

if _IS_LINUX:
    from cbase.allocator_protocol.c_shm_allocator import (
        AP_SHM_STALE_CHECK,
        AP_SHM_UNLINK_ON_MAP,
        SharedMemoryAllocator,
    )
else:  # pragma: no cover -- the test classes are skipped off-Linux
    AP_SHM_STALE_CHECK = AP_SHM_UNLINK_ON_MAP = SharedMemoryAllocator = None

logger = logging.getLogger(__name__)

# Raw shm_open / shm_unlink via libc: creates legacy objects independent
# of cbase so the cleanup paths under test are exercised for real.
# ctypes.CDLL(None) is not supported on Windows -- None there (the test
# classes are skipped off-Linux anyway).
if _IS_LINUX:
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _LIBC.shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    _LIBC.shm_open.restype = ctypes.c_int
    _LIBC.shm_unlink.argtypes = [ctypes.c_char_p]
    _LIBC.shm_unlink.restype = ctypes.c_int
    _LIBC.ftruncate.argtypes = [ctypes.c_int, ctypes.c_long]
    _LIBC.ftruncate.restype = ctypes.c_int
else:  # pragma: no cover -- the test classes are skipped off-Linux
    _LIBC = None

# Child script: creates an allocator + page + block for $AP_T06_PREFIX and
# exits WITHOUT cleanup, simulating a crash (atexit / __del__ bypassed).
_CHILD_CRASH_CODE = """
import os
from cbase.allocator_protocol.c_shm_allocator import SharedMemoryAllocator
a = SharedMemoryAllocator(shm_prefix=os.environ['AP_T06_PREFIX'])
p = a.extend(0)
b = a.calloc(4096)
b.buffer[:4] = b'DATA'
os._exit(1)
"""

# Child script: creates an allocator for $AP_T06_PREFIX (triggers the
# on-start stale scan), then exits normally.
_CHILD_SCAN_CODE = """
import os
from cbase.allocator_protocol.c_shm_allocator import SharedMemoryAllocator
a = SharedMemoryAllocator(shm_prefix=os.environ['AP_T06_PREFIX'])
print('scan-done', flush=True)
"""


def _shm_names(prefix: str) -> list[str]:
    """Sorted /dev/shm entries under ``prefix`` (leading '/' stripped)."""
    pfx = prefix[1:] if prefix.startswith('/') else prefix
    return sorted(n for n in os.listdir('/dev/shm') if n.startswith(pfx))


def _make_legacy_object(name: str, size: int = 4096) -> None:
    """Create a raw named SHM object the way a pre-fix cbase would leave
    it behind (created and never unlinked)."""
    fd = _LIBC.shm_open(name.encode(), os.O_CREAT | os.O_RDWR, 0o600)
    if fd < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), name)
    try:
        if _LIBC.ftruncate(fd, size) != 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), name)
    finally:
        os.close(fd)


def _unlink_legacy_object(name: str) -> None:
    _LIBC.shm_unlink(name.encode())


# ---------------------------------------------------------------------------
# Compile-time toggles
# ---------------------------------------------------------------------------

@unittest.skipUnless(_IS_LINUX, "POSIX /dev/shm cleanup tests are Linux-only")
class TestShmCleanupConstants(unittest.TestCase):
    """Cleanup behavior must be enabled in the default build."""

    def test_00_stale_check_default_on(self):
        self.assertEqual(AP_SHM_STALE_CHECK, 1)

    def test_01_unlink_on_map_default_on(self):
        self.assertEqual(AP_SHM_UNLINK_ON_MAP, 1)


# ---------------------------------------------------------------------------
# Unlink-while-mapped
# ---------------------------------------------------------------------------

@unittest.skipUnless(_IS_LINUX, "POSIX /dev/shm cleanup tests are Linux-only")
class TestShmUnlinkOnMap(unittest.TestCase):
    """Names vanish at creation time; nothing persists after a crash."""

    def _prefix(self) -> str:
        return f'/c_t06_um_{os.getpid()}_{id(self):x}'

    def test_00_names_gone_while_allocator_alive(self):
        pfx = self._prefix()
        a = SharedMemoryAllocator(shm_prefix=pfx)
        a.extend(0)
        a.calloc(1024)
        # Both meta and page names must already be gone from /dev/shm.
        self.assertEqual(_shm_names(pfx), [])
        del a
        gc.collect()

    def test_01_names_gone_after_destroy(self):
        pfx = self._prefix()
        a = SharedMemoryAllocator(shm_prefix=pfx)
        a.extend(0)
        a.calloc(1024)
        del a
        gc.collect()
        self.assertEqual(_shm_names(pfx), [])

    def test_02_crash_child_leaks_nothing(self):
        """A child that dies via os._exit leaves no SHM names behind."""
        pfx = f'/c_t06_crash_{os.getpid()}'
        env = dict(os.environ, AP_T06_PREFIX=pfx)
        proc = subprocess.run(
            [sys.executable, '-c', _CHILD_CRASH_CODE],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(_shm_names(pfx), [])


# ---------------------------------------------------------------------------
# On-start stale scan -- dead creators (legacy objects)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_IS_LINUX, "POSIX /dev/shm cleanup tests are Linux-only")
class TestShmStaleScanDeadCreator(unittest.TestCase):
    """Legacy objects with a dead creator are unlinked on allocator start,
    with ``[AP] [STALE_SHM]`` logged to stderr."""

    @staticmethod
    def _dead_pid() -> int:
        """PID of a short-lived, fully reaped process."""
        proc = subprocess.Popen([sys.executable, '-c', 'pass'])
        proc.wait()
        return proc.pid

    def _prefix(self) -> str:
        return f'/c_t06_dc_{os.getpid()}_{id(self):x}'

    def _scan_in_subprocess(self, pfx: str) -> str:
        """Run the on-start scan in a child and return its stderr."""
        env = dict(os.environ, AP_T06_PREFIX=pfx)
        proc = subprocess.run(
            [sys.executable, '-c', _CHILD_SCAN_CODE],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stderr

    def test_00_legacy_dead_meta_cleaned_on_start(self):
        pfx = self._prefix()
        dead = self._dead_pid()
        with self.assertRaises(ProcessLookupError):
            os.kill(dead, 0)
        meta_name = f'{pfx}_ac_{dead:x}_7f0000000000'
        _make_legacy_object(meta_name)
        self.assertIn(meta_name[1:], _shm_names(pfx))

        stderr = self._scan_in_subprocess(pfx)

        self.assertEqual(_shm_names(pfx), [])
        self.assertIn('[AP] [STALE_SHM]', stderr)
        self.assertIn(meta_name, stderr)
        self.assertIn('dead', stderr)

    def test_01_legacy_dead_page_cleaned_on_start(self):
        """Regression: page names ({prefix}_pg_{pid}_{region}_{idx}) parse
        correctly and are detected as stale."""
        pfx = self._prefix()
        dead = self._dead_pid()
        with self.assertRaises(ProcessLookupError):
            os.kill(dead, 0)
        page_name = f'{pfx}_pg_{dead:x}_7f0000000000_0'
        _make_legacy_object(page_name)
        self.assertIn(page_name[1:], _shm_names(pfx))

        stderr = self._scan_in_subprocess(pfx)

        self.assertEqual(_shm_names(pfx), [])
        self.assertIn('[AP] [STALE_SHM]', stderr)
        self.assertIn(page_name, stderr)

    def test_02_live_creator_not_cleaned(self):
        """A legacy-named object with OUR live pid must survive the scan
        (start-time guard: we predate the object)."""
        pfx = self._prefix()
        meta_name = f'{pfx}_ac_{os.getpid():x}_7f0000000000'
        _make_legacy_object(meta_name)
        self.addCleanup(_unlink_legacy_object, meta_name)
        self.assertIn(meta_name[1:], _shm_names(pfx), 'legacy object not created')

        stderr = self._scan_in_subprocess(pfx)

        self.assertIn(meta_name[1:], _shm_names(pfx))
        self.assertNotIn(meta_name, stderr)

    def test_03_cleanup_dangling_method(self):
        pfx = self._prefix()
        dead = self._dead_pid()
        with self.assertRaises(ProcessLookupError):
            os.kill(dead, 0)
        meta_name = f'{pfx}_ac_{dead:x}_7f0000000000'
        page_name = f'{pfx}_pg_{dead:x}_7f0000000000_0'
        _make_legacy_object(meta_name)
        _make_legacy_object(page_name)

        # Different prefix so the startup scan does not pre-clean them;
        # cleanup_dangling(pfx) must do the work.
        a = SharedMemoryAllocator(shm_prefix=f'{pfx}_holder')
        a.cleanup_dangling(pfx)
        del a
        gc.collect()

        self.assertEqual(_shm_names(pfx), [])

    def test_04_dangling_lists_agree_with_c_scan(self):
        pfx = self._prefix()
        dead = self._dead_pid()
        with self.assertRaises(ProcessLookupError):
            os.kill(dead, 0)
        meta_name = f'{pfx}_ac_{dead:x}_7f0000000000'
        page_name = f'{pfx}_pg_{dead:x}_7f0000000000_0'
        _make_legacy_object(meta_name)
        _make_legacy_object(page_name)
        self.addCleanup(_unlink_legacy_object, meta_name)
        self.addCleanup(_unlink_legacy_object, page_name)

        # A live allocator (different prefix) so the scan does not fire here.
        a = SharedMemoryAllocator(shm_prefix=f'{pfx}_live')
        self.assertIn(meta_name, a.dangling(pfx))
        self.assertIn(page_name, a.dangling_pages(pfx))
        del a
        gc.collect()


# ---------------------------------------------------------------------------
# On-start stale scan -- zombie creators
# ---------------------------------------------------------------------------

@unittest.skipUnless(_IS_LINUX, "POSIX /dev/shm cleanup tests are Linux-only")
class TestShmStaleScanZombie(unittest.TestCase):
    """A zombie (exited but unreaped) creator's objects are stale: the
    plain kill(pid, 0) probe alone would miss them."""

    def test_00_zombie_cleaned_on_start(self):
        pfx = f'/c_t06_zc_{os.getpid()}_{id(self):x}'

        # Fork a child that waits for our signal, then exits hard.
        r_fd, w_fd = os.pipe()
        pid = os.fork()
        if pid == 0:  # child
            os.close(w_fd)
            os.read(r_fd, 1)
            os._exit(0)

        # Parent: name legacy objects after the (soon zombie) child pid.
        os.close(r_fd)

        def _release_and_reap() -> None:
            # If the test failed before writing the byte, the child is
            # still blocked in read(); releasing it first keeps waitpid
            # from blocking forever on a live child.
            with suppress(OSError):
                os.write(w_fd, b'x')
                os.close(w_fd)
            os.waitpid(pid, 0)

        self.addCleanup(_release_and_reap)
        meta_name = f'{pfx}_ac_{pid:x}_7f0000000000'
        page_name = f'{pfx}_pg_{pid:x}_7f0000000000_0'
        _make_legacy_object(meta_name)
        _make_legacy_object(page_name)

        os.write(w_fd, b'x')
        os.close(w_fd)

        # Wait until the child is a zombie (not reaped).
        deadline = time.monotonic() + 5.0
        state = ''
        while time.monotonic() < deadline:
            with open(f'/proc/{pid}/stat', encoding='ascii') as f:
                state = f.read().rsplit(')', 1)[1].split()[0]
            if state == 'Z':
                break
            time.sleep(0.01)
        self.assertEqual(state, 'Z', f'child {pid} did not become a zombie')

        # The on-start scan must unlink the zombie's objects and log it.
        env = dict(os.environ, AP_T06_PREFIX=pfx)
        proc = subprocess.run(
            [sys.executable, '-c', _CHILD_SCAN_CODE],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        self.assertEqual(_shm_names(pfx), [])
        self.assertIn('[AP] [STALE_SHM]', proc.stderr)
        self.assertIn(meta_name, proc.stderr)
        self.assertIn(page_name, proc.stderr)
        self.assertIn('zombie', proc.stderr)


if __name__ == '__main__':
    unittest.main()
