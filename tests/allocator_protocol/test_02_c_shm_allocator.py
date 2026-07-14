"""Tests for the shared-memory allocator (c_shm_allocator).

Every test case uses a fresh SharedMemoryAllocator instance so that state
(pages, free list, SHM objects) does not leak between tests.

Requires /dev/shm (POSIX shared memory).
"""
import gc
import unittest

from cbase.allocator_protocol.c_shm_allocator import (
    AP_SHM_ALLOCATOR_PREFIX,
    AP_SHM_AUTOPAGE_ALIGNMENT,
    AP_SHM_AUTOPAGE_CAPACITY,
    AP_SHM_AUTOPAGE_CAPACITY_MAX,
    AP_SHM_NAME_LEN,
    SharedMemoryAllocator,
    SharedMemoryBlock,
    SharedMemoryPage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_roundup(size: int) -> int:
    return (size + AP_SHM_AUTOPAGE_ALIGNMENT - 1) & ~(AP_SHM_AUTOPAGE_ALIGNMENT - 1)


class _FreshAllocatorMixin:
    """Mixin that provides a fresh allocator per test via setUp / tearDown."""

    allocator: SharedMemoryAllocator

    def setUp(self):
        self.allocator = SharedMemoryAllocator()

    def tearDown(self):
        del self.allocator
        gc.collect()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestShmConstants(unittest.TestCase):
    """Verify compile-time constants are exported correctly."""

    def test_default_autopage_capacity(self):
        self.assertEqual(AP_SHM_AUTOPAGE_CAPACITY, 64 * 1024)

    def test_autopage_capacity_max(self):
        self.assertEqual(AP_SHM_AUTOPAGE_CAPACITY_MAX, 16 * 1024 * 1024)

    def test_autopage_alignment(self):
        self.assertEqual(AP_SHM_AUTOPAGE_ALIGNMENT, 4 * 1024)

    def test_name_len(self):
        self.assertEqual(AP_SHM_NAME_LEN, 256)

    def test_prefixes(self):
        self.assertTrue(AP_SHM_ALLOCATOR_PREFIX.startswith('/'))


# ---------------------------------------------------------------------------
# Constructor / creation
# ---------------------------------------------------------------------------

class TestShmAllocatorCreation(unittest.TestCase):
    """Creating and destroying SharedMemoryAllocator instances."""

    def test_constructor_creates_instance(self):
        a = SharedMemoryAllocator()
        self.assertIsInstance(a, SharedMemoryAllocator)
        self.assertTrue(a.owner)

    def test_multiple_instances_independent(self):
        a1 = SharedMemoryAllocator()
        a2 = SharedMemoryAllocator()
        self.assertIsNot(a1, a2)

    def test_destroy_and_recreate(self):
        a1 = SharedMemoryAllocator()
        del a1
        gc.collect()
        a2 = SharedMemoryAllocator()
        self.assertIsNotNone(a2)

    def test_custom_region_size(self):
        a = SharedMemoryAllocator(1 << 30)  # 1 GiB
        self.assertIsInstance(a, SharedMemoryAllocator)


# ---------------------------------------------------------------------------
# Config properties
# ---------------------------------------------------------------------------

class TestShmAllocatorConfig(_FreshAllocatorMixin, unittest.TestCase):
    """The three autopage config fields on shm_allocator."""

    def test_default_autopage_capacity(self):
        self.assertEqual(self.allocator.autopage_capacity,
                         AP_SHM_AUTOPAGE_CAPACITY)

    def test_default_autopage_capacity_max(self):
        self.assertEqual(self.allocator.autopage_capacity_max,
                         AP_SHM_AUTOPAGE_CAPACITY_MAX)

    def test_default_autopage_alignment(self):
        self.assertEqual(self.allocator.autopage_alignment,
                         AP_SHM_AUTOPAGE_ALIGNMENT)

    def test_set_autopage_capacity_affects_extend(self):
        new_cap = 8192
        self.allocator.autopage_capacity = new_cap
        self.assertEqual(self.allocator.autopage_capacity, new_cap)
        page = self.allocator.extend(0)
        self.assertEqual(page.capacity, new_cap)

    def test_set_autopage_alignment_affects_roundup(self):
        self.allocator.autopage_alignment = 8192
        page = self.allocator.extend(5000)
        self.assertEqual(page.capacity % 8192, 0)
        self.assertGreaterEqual(page.capacity, 5000)


# ---------------------------------------------------------------------------
# calloc
# ---------------------------------------------------------------------------

class TestShmCalloc(_FreshAllocatorMixin, unittest.TestCase):

    def test_calloc_size_1(self):
        b = self.allocator.calloc(1)
        self.assertEqual(b.size, 1)
        self.assertGreaterEqual(b.capacity, 1)

    def test_calloc_16_zeroed(self):
        b = self.allocator.calloc(16)
        self.assertEqual(bytes(b.buffer), b'\x00' * 16)

    def test_calloc_1k_write_read(self):
        b = self.allocator.calloc(1024)
        pattern = bytes(i & 0xFF for i in range(1024))
        b.buffer[:] = pattern
        self.assertEqual(bytes(b.buffer), pattern)

    def test_calloc_has_page_address(self):
        b = self.allocator.calloc(256)
        addr = b.page_address
        self.assertIsNotNone(addr)
        self.assertTrue(addr.startswith('0x'))

    def test_calloc_consecutive_same_page(self):
        b1 = self.allocator.calloc(128)
        b2 = self.allocator.calloc(128)
        self.assertEqual(b1.page_address, b2.page_address)
        self.assertNotEqual(b1.address, b2.address)

    def test_calloc_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.calloc(0)

    def test_calloc_with_lock_false(self):
        b = self.allocator.calloc(64, with_lock=False)
        self.assertEqual(b.size, 64)

    def test_calloc_address_is_hex(self):
        b = self.allocator.calloc(64)
        self.assertTrue(b.address.startswith('0x'))


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

class TestShmRequest(_FreshAllocatorMixin, unittest.TestCase):

    def test_request_basic(self):
        b = self.allocator.request(512)
        self.assertEqual(b.size, 512)
        self.assertGreaterEqual(b.capacity, 512)

    def test_request_zeroed(self):
        b = self.allocator.request(256)
        self.assertEqual(bytes(b.buffer), b'\x00' * 256)

    def test_request_reuses_freed_block(self):
        b1 = self.allocator.calloc(128)
        addr1 = b1.address
        self.allocator.free(b1)

        b2 = self.allocator.request(128)
        self.assertEqual(b2.address, addr1)

    def test_request_zeroed_after_reuse(self):
        b1 = self.allocator.calloc(64)
        b1.buffer[:4] = b'DIRT'
        self.allocator.free(b1)

        b2 = self.allocator.request(64)
        self.assertEqual(bytes(b2.buffer[:4]), b'\x00' * 4)

    def test_request_lifo_free_list(self):
        b1 = self.allocator.calloc(32)
        b2 = self.allocator.calloc(64)
        addr1, addr2 = b1.address, b2.address

        self.allocator.free(b2)
        self.allocator.free(b1)

        b3 = self.allocator.request(16)
        b4 = self.allocator.request(48)
        self.assertEqual(b3.address, addr1)
        self.assertEqual(b4.address, addr2)

    def test_request_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.request(0)

    def test_request_scan_all_pages_false(self):
        b = self.allocator.request(32, scan_all_pages=False)
        self.assertEqual(b.size, 32)

    def test_request_scan_all_pages_true_reuses_across_pages(self):
        """A freed block on an older page is found with scan_all_pages=True."""
        p1 = self.allocator.extend(8192)
        b1 = self.allocator.calloc(64)
        addr1 = b1.address
        # Force a second page so b1 is no longer on the active page
        p2 = self.allocator.extend(8192)
        self.allocator.free(b1)
        b2 = self.allocator.request(64, scan_all_pages=True)
        self.assertEqual(b2.address, addr1,
                         "scan_all_pages=True must find freed block on older page")

    def test_request_with_lock_false(self):
        b = self.allocator.request(64, with_lock=False)
        self.assertEqual(b.size, 64)


# ---------------------------------------------------------------------------
# free
# ---------------------------------------------------------------------------

class TestShmFree(_FreshAllocatorMixin, unittest.TestCase):

    def test_free_increases_free_list(self):
        free_before = len(list(self.allocator.free_list()))
        b = self.allocator.calloc(200)
        self.allocator.free(b)
        free_after = len(list(self.allocator.free_list()))
        self.assertEqual(free_after, free_before + 1)

    def test_free_block_appears_in_free_list(self):
        b = self.allocator.calloc(128)
        addr = b.address
        self.allocator.free(b)
        addrs = {f.address for f in self.allocator.free_list()}
        self.assertIn(addr, addrs)

    def test_double_free_is_noop_second_time(self):
        """Freeing an already-freed block: second free is a no-op."""
        b = self.allocator.calloc(256)
        self.allocator.free(b)
        self.allocator.free(b)  # must not crash

    def test_free_with_lock_false(self):
        b = self.allocator.calloc(64)
        self.allocator.free(b, with_lock=False)

    def test_free_many(self):
        blocks = [self.allocator.calloc(128) for _ in range(10)]
        addrs = [b.address for b in blocks]
        for b in blocks:
            self.allocator.free(b)
        free_addrs = {f.address for f in self.allocator.free_list()}
        for addr in addrs:
            self.assertIn(addr, free_addrs)


# ---------------------------------------------------------------------------
# reclaim
# ---------------------------------------------------------------------------

class TestShmReclaim(_FreshAllocatorMixin, unittest.TestCase):

    def test_reclaim_reduces_page_occupied(self):
        page = self.allocator.active_page or self.allocator.extend(0)
        occupied_before = page.occupied

        b = self.allocator.calloc(512)
        # calloc must increase occupied by cap_net + overhead
        self.assertGreater(page.occupied, occupied_before)
        occupied_after_calloc = page.occupied

        self.allocator.free(b)
        # free does NOT change occupied (only size=0, moved to free_list)
        self.assertEqual(page.occupied, occupied_after_calloc)

        page.reclaim()
        # reclaim returns freed space — occupied back to original
        self.assertEqual(page.occupied, occupied_before)

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

class TestShmExtend(_FreshAllocatorMixin, unittest.TestCase):

    def test_extend_default_creates_page(self):
        self.assertEqual(self.allocator.mapped_pages, 0)
        page = self.allocator.extend(0)
        self.assertIsInstance(page, SharedMemoryPage)
        self.assertEqual(self.allocator.mapped_pages, 1)

    def test_extend_default_capacity(self):
        page = self.allocator.extend(0)
        self.assertEqual(page.capacity, AP_SHM_AUTOPAGE_CAPACITY)

    def test_extend_exact_is_page_aligned(self):
        page = self.allocator.extend(5000)
        self.assertGreaterEqual(page.capacity, 5000)
        self.assertEqual(page.capacity, _page_roundup(5000))

    def test_extend_multiple(self):
        for _ in range(3):
            self.allocator.extend(4096)
        self.assertEqual(self.allocator.mapped_pages, 3)

    def test_second_page_doubles(self):
        p1 = self.allocator.extend(0)
        p2 = self.allocator.extend(0)
        expected = min(p1.capacity * 2, AP_SHM_AUTOPAGE_CAPACITY_MAX)
        self.assertEqual(p2.capacity, expected)

    def test_page_capacity_always_aligned(self):
        pages = [self.allocator.extend(0) for _ in range(3)]
        for p in pages:
            self.assertEqual(p.capacity % AP_SHM_AUTOPAGE_ALIGNMENT, 0)

    def test_extend_with_lock_false(self):
        page = self.allocator.extend(1024, with_lock=False)
        self.assertGreater(page.capacity, 0)


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------

class TestShmIteration(_FreshAllocatorMixin, unittest.TestCase):

    def test_pages_empty_initially(self):
        self.assertEqual(list(self.allocator.pages()), [])

    def test_pages_after_extend(self):
        self.allocator.extend(4096)
        pages = list(self.allocator.pages())
        self.assertEqual(len(pages), 1)
        self.assertIsInstance(pages[0], SharedMemoryPage)

    def test_pages_newest_first(self):
        p1 = self.allocator.extend(4096)
        p2 = self.allocator.extend(8192)
        pages = list(self.allocator.pages())
        self.assertEqual(pages[0].address, p2.address)
        self.assertEqual(pages[1].address, p1.address)

    def test_allocated_empty_initially(self):
        self.assertEqual(list(self.allocator.allocated()), [])

    def test_allocated_after_calloc(self):
        b = self.allocator.calloc(128)
        allocated = list(self.allocator.allocated())
        addrs = {a.address for a in allocated}
        self.assertIn(b.address, addrs)

    def test_free_list_empty_initially(self):
        self.assertEqual(list(self.allocator.free_list()), [])

    def test_allocated_still_includes_freed_until_reclaimed(self):
        """SHM free moves the block to the free_list but does NOT unlink it
        from the page's allocated chain.  Only reclaim removes it from
        the allocated list."""
        b = self.allocator.calloc(256)
        addr = b.address
        self.allocator.free(b)
        # Freed block is still in allocated() (size=0, on free_list)
        allocated_addrs = {a.address for a in self.allocator.allocated()}
        self.assertIn(addr, allocated_addrs,
                      "SHM free keeps block in allocated list")
        # After reclaim, it is removed
        self.allocator.reclaim()
        allocated_addrs = {a.address for a in self.allocator.allocated()}
        self.assertNotIn(addr, allocated_addrs,
                         "block must be gone from allocated() after reclaim")

    def test_free_list_after_reclaim(self):
        b = self.allocator.calloc(64)
        self.allocator.free(b)
        self.assertGreater(len(list(self.allocator.free_list())), 0)
        self.allocator.reclaim()
        self.assertEqual(list(self.allocator.free_list()), [],
                         "free_list must be empty after reclaim")

    def test_calloc_triggers_implicit_extend(self):
        """First calloc on a fresh allocator implicitly extends a page."""
        self.assertEqual(self.allocator.mapped_pages, 0)
        b = self.allocator.calloc(64)
        self.assertGreaterEqual(self.allocator.mapped_pages, 1)
        self.assertIsNotNone(self.allocator.active_page)

    def test_page_has_name(self):
        page = self.allocator.extend(4096)
        self.assertIsNotNone(page.name)
        # Page names are: {prefix}_pg_{pid}_{page_idx}
        self.assertIn('_pg_', page.name)


# ---------------------------------------------------------------------------
# Memory patterns
# ---------------------------------------------------------------------------

class TestShmPatterns(_FreshAllocatorMixin, unittest.TestCase):

    def test_write_full_block_4k(self):
        size = 4096
        b = self.allocator.calloc(size)
        pattern = bytes((i * 7 + 13) & 0xFF for i in range(size))
        b.buffer[:] = pattern
        self.assertEqual(bytes(b.buffer), pattern)

    def test_two_blocks_independent(self):
        b1 = self.allocator.calloc(256)
        b2 = self.allocator.calloc(256)
        b1.buffer[:4] = b'\x01\x02\x03\x04'
        b2.buffer[:4] = b'\xaa\xbb\xcc\xdd'
        self.assertEqual(bytes(b1.buffer[:4]), b'\x01\x02\x03\x04')
        self.assertEqual(bytes(b2.buffer[:4]), b'\xaa\xbb\xcc\xdd')

    def test_alloc_free_cycle(self):
        addrs = set()
        for i in range(20):
            b = self.allocator.calloc(64)
            addrs.add(b.address)
            b.buffer[0] = bytes([i & 0xFF])
            self.allocator.free(b)
        b2 = self.allocator.request(64)
        self.assertIn(b2.address, addrs)
        self.assertEqual(b2.buffer[0], b'\x00')


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestShmEdgeCases(_FreshAllocatorMixin, unittest.TestCase):

    def test_allocator_repr(self):
        r = repr(self.allocator)
        self.assertIn('SharedMemoryAllocator', r)

    def test_reclaim_without_any_alloc(self):
        self.allocator.reclaim()

    def test_gc_of_allocator(self):
        a = SharedMemoryAllocator()
        a.calloc(256)
        a.extend(4096)
        del a
        gc.collect()

    def test_get_pid(self):
        pid = self.allocator.pid
        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)

    def test_dangling_no_error(self):
        """dangling() and cleanup_dangling() should not raise."""
        self.allocator.dangling()
        self.allocator.dangling_pages()
        self.allocator.cleanup_dangling()


if __name__ == '__main__':
    unittest.main()
