"""Tests for NT SHM lifecycle cleanup (c_nt_shm_allocator).

Contracts (Windows only; skipped on POSIX):
    - AP_SHM_STALE_CHECK / AP_SHM_UNLINK_ON_MAP default to 1.
    - Unlink-while-mapped: after creation, allocator and page section
      names are not openable by name (the creating handle is closed and
      the object survives only via the mapped view).
    - The on-start scan detects a mapping named after a dead creator pid
      and logs ``[AP] [STALE_SHM] ...`` to stderr.  (On Windows the object
      itself is destroyed by the kernel when the last handle closes, so
      the scan only nudges and reports.)
    - dangling() lists a legacy mapping named after a dead pid while a
      handle still keeps the object alive.

C-level ``fprintf(stderr, ...)`` writes to fd 2; log-content assertions
therefore run the scan in a subprocess with ``stderr=PIPE``.
"""
import ctypes
import gc
import os
import subprocess
import sys
import unittest

# Child script: keeps a legacy mapping (dead-pid name) alive via an open
# handle, then creates an allocator for the same prefix (triggering the
# on-start scan), then exits.
_CHILD_LEGACY_SCAN_CODE = """
import ctypes
import os
from cbase.allocator_protocol.c_nt_shm_allocator import NtSharedMemoryAllocator

k32 = ctypes.windll.kernel32
pfx = os.environ['AP_T07_PREFIX']
dead = int(os.environ['AP_T07_DEADPID'])
name = f"Global\\\\{pfx[1:]}_ac_{dead:x}"
CreateFileMappingW = k32.CreateFileMappingW
CreateFileMappingW.restype = ctypes.c_void_p
CreateFileMappingW.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
    ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p,
]
h = CreateFileMappingW(ctypes.c_void_p(-1), None, 0x04, 0, 0x20000, name)
assert h, f"CreateFileMappingW failed: {ctypes.GetLastError()}"

a = NtSharedMemoryAllocator(shm_prefix=pfx)
print('scan-done', flush=True)
"""


@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmCleanupConstants(unittest.TestCase):
    """Cleanup behavior must be enabled in the default build."""

    def test_00_stale_check_default_on(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_STALE_CHECK,
        )
        self.assertEqual(AP_SHM_STALE_CHECK, 1)

    def test_01_unlink_on_map_default_on(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_UNLINK_ON_MAP,
        )
        self.assertEqual(AP_SHM_UNLINK_ON_MAP, 1)


@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmUnlinkOnMap(unittest.TestCase):
    """Section names are not openable while the allocator is alive."""

    ERROR_FILE_NOT_FOUND = 2

    @staticmethod
    def _open_mapping(utf8_name: str) -> bool:
        """True when a Global\\ mapping with ``utf8_name`` (leading '/' ok)
        can be opened read-only."""
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenFileMappingW.restype = ctypes.c_void_p
        k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        base = utf8_name[1:] if utf8_name.startswith('/') else utf8_name
        h = k32.OpenFileMappingW(0x0004, False, f"Global\\{base}")
        if h:
            k32.CloseHandle(h)
        return h is not None

    def _prefix(self) -> str:
        return f'/c_nt07_um_{os.getpid()}_{id(self):x}'

    def test_00_meta_name_gone_while_alive(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        pfx = self._prefix()
        a = NtSharedMemoryAllocator(shm_prefix=pfx)
        meta_name = f"{pfx}_ac_{a.pid:x}"
        self.assertFalse(
            self._open_mapping(meta_name),
            f"meta mapping {meta_name} still openable by name",
        )
        del a
        gc.collect()

    def test_01_page_name_gone_while_alive(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        pfx = self._prefix()
        a = NtSharedMemoryAllocator(shm_prefix=pfx)
        page = a.extend(0)
        self.assertFalse(
            self._open_mapping(page["name"]),
            f"page mapping {page['name']} still openable by name",
        )
        del a
        gc.collect()


@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmStaleScanDeadCreator(unittest.TestCase):
    """The on-start scan finds mappings named after a dead pid."""

    @staticmethod
    def _dead_pid() -> int:
        """PID of a short-lived, fully reaped process, within the scan's
        covered range (< 65536)."""
        for _ in range(8):
            proc = subprocess.Popen([sys.executable, '-c', 'pass'])
            proc.wait()
            if proc.pid < 65536:
                return proc.pid
        raise unittest.SkipTest('system PIDs exhausted the scan range')

    def _prefix(self) -> str:
        return f'/c_nt07_lg_{os.getpid()}_{id(self):x}'

    def test_00_scan_logs_stale_mapping(self):
        pfx = self._prefix()
        dead = self._dead_pid()
        env = dict(os.environ, AP_T07_PREFIX=pfx, AP_T07_DEADPID=str(dead))
        proc = subprocess.run(
            [sys.executable, '-c', _CHILD_LEGACY_SCAN_CODE],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('scan-done', proc.stdout)
        self.assertIn('[AP] [STALE_SHM]', proc.stderr)
        self.assertIn(f'_ac_{dead:x}', proc.stderr)
        self.assertIn('dead', proc.stderr)

    def test_01_dangling_lists_legacy_mapping(self):
        """A mapping kept alive by our own handle is reported as dangling
        while the dead creator pid is in its name."""
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        pfx = self._prefix()
        dead = self._dead_pid()

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateFileMappingW.restype = ctypes.c_void_p
        k32.CreateFileMappingW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_wchar_p,
        ]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        name = f"Global\\{pfx[1:]}_ac_{dead:x}"
        h = k32.CreateFileMappingW(
            ctypes.c_void_p(-1), None, 0x04, 0, 0x20000, name,
        )
        self.assertTrue(h, f'CreateFileMappingW failed: {ctypes.get_last_error()}')
        self.addCleanup(k32.CloseHandle, h)

        a = NtSharedMemoryAllocator(shm_prefix=pfx)
        names = a.dangling(pfx)
        del a
        gc.collect()

        self.assertTrue(
            any(f'_ac_{dead:x}' in n for n in names),
            f'dangling() missed legacy mapping named after pid {dead:x}: {names}',
        )


if __name__ == '__main__':
    unittest.main()
