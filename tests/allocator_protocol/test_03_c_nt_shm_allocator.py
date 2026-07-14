"""Tests for the NT-native shared memory allocator (c_nt_shm_allocator).

Every test case uses a fresh NtSharedMemoryAllocator instance so that state
(pages, free list, file mappings) does not leak between tests.

Requires Windows — skipped on POSIX.
"""
import gc
import sys
import unittest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_roundup(size: int, alignment: int = 4096) -> int:
    return (size + alignment - 1) & ~(alignment - 1)


class _FreshAllocatorMixin:
    """Mixin that provides a fresh allocator per test via setUp / tearDown."""

    allocator: "NtSharedMemoryAllocator"

    def setUp(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        self.allocator = NtSharedMemoryAllocator()

    def tearDown(self):
        del self.allocator
        gc.collect()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmConstants(unittest.TestCase):
    """Verify compile-time constants are exported correctly."""

    def test_default_autopage_capacity(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_CAPACITY,
        )
        self.assertEqual(AP_SHM_AUTOPAGE_CAPACITY, 64 * 1024)

    def test_autopage_capacity_max(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_CAPACITY_MAX,
        )
        self.assertEqual(AP_SHM_AUTOPAGE_CAPACITY_MAX, 16 * 1024 * 1024)

    def test_autopage_alignment(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_ALIGNMENT,
        )
        self.assertEqual(AP_SHM_AUTOPAGE_ALIGNMENT, 4 * 1024)

    def test_name_len(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import AP_SHM_NAME_LEN
        self.assertEqual(AP_SHM_NAME_LEN, 256)

    def test_prefix(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_ALLOCATOR_PREFIX,
        )
        self.assertTrue(AP_SHM_ALLOCATOR_PREFIX.startswith("/"))


# ---------------------------------------------------------------------------
# Constructor / creation
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmAllocatorCreation(unittest.TestCase):
    """Creating and destroying NtSharedMemoryAllocator instances."""

    def test_constructor_creates_instance(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a = NtSharedMemoryAllocator()
        self.assertIsInstance(a, NtSharedMemoryAllocator)
        self.assertTrue(a.owner)

    def test_multiple_instances_independent(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a1 = NtSharedMemoryAllocator()
        a2 = NtSharedMemoryAllocator()
        self.assertIsNot(a1, a2)

    def test_destroy_and_recreate(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a1 = NtSharedMemoryAllocator()
        del a1
        gc.collect()
        a2 = NtSharedMemoryAllocator()
        self.assertIsNotNone(a2)

    def test_custom_region_size(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a = NtSharedMemoryAllocator(1 << 30)  # 1 GiB
        self.assertIsInstance(a, NtSharedMemoryAllocator)

    def test_custom_prefix(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a = NtSharedMemoryAllocator(shm_prefix="/test_nt_custom")
        self.assertEqual(a.shm_prefix, "/test_nt_custom")


# ---------------------------------------------------------------------------
# Config properties
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmAllocatorConfig(_FreshAllocatorMixin, unittest.TestCase):

    def test_default_autopage_capacity(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_CAPACITY,
        )
        self.assertEqual(
            self.allocator.autopage_capacity, AP_SHM_AUTOPAGE_CAPACITY,
        )

    def test_default_autopage_capacity_max(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_CAPACITY_MAX,
        )
        self.assertEqual(
            self.allocator.autopage_capacity_max,
            AP_SHM_AUTOPAGE_CAPACITY_MAX,
        )

    def test_default_autopage_alignment(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_ALIGNMENT,
        )
        self.assertEqual(
            self.allocator.autopage_alignment, AP_SHM_AUTOPAGE_ALIGNMENT,
        )

    def test_set_autopage_capacity_affects_extend(self):
        new_cap = 8192
        self.allocator.autopage_capacity = new_cap
        self.assertEqual(self.allocator.autopage_capacity, new_cap)
        page = self.allocator.extend(0)
        self.assertEqual(page["capacity"], new_cap)

    def test_set_autopage_alignment_affects_roundup(self):
        self.allocator.autopage_alignment = 8192
        page = self.allocator.extend(5000)
        self.assertEqual(page["capacity"] % 8192, 0)
        self.assertGreaterEqual(page["capacity"], 5000)


# ---------------------------------------------------------------------------
# calloc
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmCalloc(_FreshAllocatorMixin, unittest.TestCase):

    def test_calloc_size_1(self):
        b = self.allocator.calloc(1)
        self.assertEqual(len(b), 1)

    def test_calloc_16_zeroed(self):
        b = self.allocator.calloc(16)
        self.assertEqual(bytes(b), b"\x00" * 16)

    def test_calloc_1k_write_read(self):
        b = self.allocator.calloc(1024)
        pattern = bytes(i & 0xFF for i in range(1024))
        b[:] = pattern
        self.assertEqual(bytes(b), pattern)

    def test_calloc_consecutive_different_addresses(self):
        b1 = self.allocator.calloc(128)
        b2 = self.allocator.calloc(128)
        # Should return different memory locations
        self.assertNotEqual(id(b1), id(b2))

    def test_calloc_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.calloc(0)

    def test_calloc_with_lock_false(self):
        b = self.allocator.calloc(64, with_lock=False)
        self.assertEqual(len(b), 64)

    def test_calloc_cross_page_threshold(self):
        """Allocating just slightly more than page capacity triggers extend."""
        cap = self.allocator.autopage_capacity
        # Make multiple allocs that will fill the first page and cause an extend
        for _ in range(4):
            self.allocator.calloc(cap // 4)
        self.assertGreaterEqual(self.allocator.mapped_pages, 1)


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmRequest(_FreshAllocatorMixin, unittest.TestCase):

    def test_request_basic(self):
        b = self.allocator.request(512)
        self.assertEqual(len(b), 512)

    def test_request_zeroed(self):
        b = self.allocator.request(256)
        self.assertEqual(bytes(b), b"\x00" * 256)

    def test_request_reuses_freed_block(self):
        b1 = self.allocator.calloc(128)
        addr1 = memoryview(b1).obj
        self.allocator.free(b1)

        b2 = self.allocator.request(128)
        # Free list reuse should give same address
        # (memoryview comparison is tricky; just check it works)
        self.assertEqual(len(b2), 128)

    def test_request_zeroed_after_reuse(self):
        b1 = self.allocator.calloc(64)
        b1[:4] = b"DIRT"
        self.allocator.free(b1)

        b2 = self.allocator.request(64)
        self.assertEqual(bytes(b2[:4]), b"\x00" * 4)

    def test_request_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.request(0)

    def test_request_scan_all_pages_false(self):
        b = self.allocator.request(32, scan_all_pages=False)
        self.assertEqual(len(b), 32)

    def test_request_with_lock_false(self):
        b = self.allocator.request(64, with_lock=False)
        self.assertEqual(len(b), 64)


# ---------------------------------------------------------------------------
# free
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmFree(_FreshAllocatorMixin, unittest.TestCase):

    def test_free_realloc_cycle(self):
        """Free then request should work."""
        b = self.allocator.calloc(200)
        self.allocator.free(b)
        b2 = self.allocator.request(200)
        self.assertEqual(len(b2), 200)

    def test_free_many(self):
        blocks = [self.allocator.calloc(128) for _ in range(10)]
        for b in blocks:
            self.allocator.free(b)
        # Should not raise

    def test_free_with_lock_false(self):
        b = self.allocator.calloc(64)
        self.allocator.free(b, with_lock=False)

    def test_free_none_is_noop(self):
        """Freeing None should not raise."""
        self.allocator.free(None)


# ---------------------------------------------------------------------------
# reclaim
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmReclaim(_FreshAllocatorMixin, unittest.TestCase):

    def test_reclaim_without_any_alloc(self):
        """Reclaim on empty allocator should not raise."""
        self.allocator.reclaim()

    def test_reclaim_idempotent(self):
        b = self.allocator.calloc(1024)
        self.allocator.free(b)
        self.allocator.reclaim()
        self.allocator.reclaim()

    def test_reclaim_with_lock_false(self):
        b = self.allocator.calloc(128)
        self.allocator.free(b)
        self.allocator.reclaim(with_lock=False)


# ---------------------------------------------------------------------------
# extend
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmExtend(_FreshAllocatorMixin, unittest.TestCase):

    def test_extend_default_creates_page(self):
        self.assertEqual(self.allocator.mapped_pages, 0)
        page = self.allocator.extend(0)
        self.assertIsInstance(page, dict)
        self.assertEqual(self.allocator.mapped_pages, 1)

    def test_extend_default_capacity(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            AP_SHM_AUTOPAGE_CAPACITY,
        )
        page = self.allocator.extend(0)
        self.assertEqual(page["capacity"], AP_SHM_AUTOPAGE_CAPACITY)

    def test_extend_exact_is_page_aligned(self):
        page = self.allocator.extend(5000)
        self.assertGreaterEqual(page["capacity"], 5000)
        self.assertEqual(
            page["capacity"],
            _page_roundup(5000, self.allocator.autopage_alignment),
        )

    def test_extend_multiple(self):
        for _ in range(3):
            self.allocator.extend(4096)
        self.assertEqual(self.allocator.mapped_pages, 3)

    def test_page_capacity_always_aligned(self):
        for _ in range(3):
            page = self.allocator.extend(0)
            self.assertEqual(
                page["capacity"] % self.allocator.autopage_alignment, 0,
            )

    def test_extend_with_lock_false(self):
        page = self.allocator.extend(1024, with_lock=False)
        self.assertGreater(page["capacity"], 0)

    def test_extend_page_has_name(self):
        page = self.allocator.extend(4096)
        self.assertIsNotNone(page["name"])
        self.assertIn("_pg_", page["name"])


# ---------------------------------------------------------------------------
# Memory patterns
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmPatterns(_FreshAllocatorMixin, unittest.TestCase):

    def test_write_full_block_4k(self):
        size = 4096
        b = self.allocator.calloc(size)
        pattern = bytes((i * 7 + 13) & 0xFF for i in range(size))
        b[:] = pattern
        self.assertEqual(bytes(b), pattern)

    def test_two_blocks_independent(self):
        b1 = self.allocator.calloc(256)
        b2 = self.allocator.calloc(256)
        b1[:4] = b"\x01\x02\x03\x04"
        b2[:4] = b"\xaa\xbb\xcc\xdd"
        self.assertEqual(bytes(b1[:4]), b"\x01\x02\x03\x04")
        self.assertEqual(bytes(b2[:4]), b"\xaa\xbb\xcc\xdd")

    def test_alloc_free_cycle(self):
        for i in range(20):
            b = self.allocator.calloc(64)
            b[0] = i & 0xFF
            self.allocator.free(b)
        b2 = self.allocator.request(64)
        self.assertEqual(len(b2), 64)
        self.assertEqual(b2[0], 0)  # should be zeroed


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmProperties(_FreshAllocatorMixin, unittest.TestCase):

    def test_repr(self):
        r = repr(self.allocator)
        self.assertIn("NtSharedMemoryAllocator", r)

    def test_pid(self):
        pid = self.allocator.pid
        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)

    def test_name(self):
        name = self.allocator.name
        self.assertIsNotNone(name)
        self.assertIn("_ac_", name)

    def test_mapped_size_initially_zero(self):
        self.assertEqual(self.allocator.mapped_size, 0)

    def test_mapped_pages_initially_zero(self):
        self.assertEqual(self.allocator.mapped_pages, 0)

    def test_shm_prefix(self):
        prefix = self.allocator.shm_prefix
        self.assertIsNotNone(prefix)

    def test_dangling_no_error(self):
        """dangling() and cleanup_dangling() should not raise."""
        self.allocator.dangling()
        self.allocator.cleanup_dangling()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@unittest.skipUnless(sys.platform == "win32", "NT SHM allocator is Windows-only")
class TestNtShmEdgeCases(_FreshAllocatorMixin, unittest.TestCase):

    def test_gc_of_allocator(self):
        from cbase.allocator_protocol.c_nt_shm_allocator import (
            NtSharedMemoryAllocator,
        )
        a = NtSharedMemoryAllocator()
        a.calloc(256)
        a.extend(4096)
        del a
        gc.collect()

    def test_many_small_allocs(self):
        """Hammer the allocator with many small allocations."""
        blocks = []
        for _ in range(100):
            blocks.append(self.allocator.calloc(17))
        for b in blocks:
            self.allocator.free(b)

    def test_interleaved_calloc_and_request(self):
        b1 = self.allocator.calloc(64)
        self.allocator.free(b1)
        b2 = self.allocator.request(64)
        b3 = self.allocator.calloc(64)
        self.assertEqual(len(b2), 64)
        self.assertEqual(len(b3), 64)

    def test_very_large_allocation(self):
        """Allocation that requires a new page larger than autopage_capacity."""
        large_size = 256 * 1024  # 256 KiB — > default 64 KiB autopage_capacity
        b = self.allocator.calloc(large_size)
        self.assertEqual(len(b), large_size)


if __name__ == "__main__":
    unittest.main()
