import subprocess
import sys
import unittest


class TestCCPBoundBufferLifecycle(unittest.TestCase):
    """Contract: c_ap_free on a bound buffer fires AP_CALLBACK_EVENT_FREE
    first, so every bound wrapper releases its reference (ref_count drops to
    the allocation's own) and the free completes gracefully instead of
    tripping the AP_ALLOC_VIGILANT shared-buffer abort.

    Expected behavior:
        - self_dealloc() on the owning wrapper frees gracefully and is
          idempotent on repeat.
        - Garbage-collecting the owning wrapper frees gracefully.
        - An AllocatorProtocol released to zero ownership frees its own
          buffer through c_ap_free without the magic-mismatch abort.

    Oracle: the child process must exit 0 and print no
    "[AP_ALLOC_VIGILANT] ERROR" on stderr (the vigilant abort exits 134).
    """

    @classmethod
    def _run_in_subprocess(cls, code: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _assert_graceful_free(self, code: str) -> None:
        proc = self._run_in_subprocess(code)
        self.assertEqual(proc.returncode, 0, f"stderr:\n{proc.stderr}")
        self.assertNotIn("[AP_ALLOC_VIGILANT] ERROR", proc.stderr)

    def test_00_self_dealloc_frees_gracefully(self) -> None:
        """self_dealloc() triggers the dealloc callbacks, releases the
        binding, and frees the buffer; a second call is a no-op."""
        self._assert_graceful_free(
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "array = CCPBoundBuffer(8)\n"
            "array.self_dealloc()\n"
            "array.self_dealloc()\n"
            "del array\n"
        )

    def test_01_gc_frees_owner_gracefully(self) -> None:
        """Garbage-collecting the owning wrapper frees the bound buffer
        without the vigilant abort."""
        self._assert_graceful_free(
            "import gc\n"
            "from cbase.allocator_protocol.c_dual_interface import CCPBoundBuffer\n"
            "array = CCPBoundBuffer(8)\n"
            "array.values = b'12345678'\n"
            "del array\n"
            "gc.collect()\n"
        )

    def test_02_allocator_protocol_dealloc_frees_gracefully(self) -> None:
        """An AllocatorProtocol released to zero ownership frees its own
        buffer through c_ap_free without the magic-mismatch abort."""
        self._assert_graceful_free(
            "import gc\n"
            "from cbase.allocator_protocol.c_allocator_protocol import AllocatorProtocol\n"
            "a = AllocatorProtocol(64)\n"
            "del a\n"
            "gc.collect()\n"
        )


if __name__ == '__main__':
    unittest.main()
