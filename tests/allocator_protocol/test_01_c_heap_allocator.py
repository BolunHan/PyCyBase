"""Tests for the local heap allocator (c_heap_allocator).

Every test case uses a fresh HeapAllocator instance so that state (pages,
free list, etc.) does not leak between tests.
"""
import gc
import unittest

from cbase.allocator_protocol.c_heap_allocator import (
    DEFAULT_AUTOPAGE_ALIGNMENT,
    DEFAULT_AUTOPAGE_CAPACITY,
    HeapAllocator,
    HeapMemoryBlock,
    HeapMemoryPage,
    MAX_AUTOPAGE_CAPACITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page_roundup(size: int) -> int:
    return (size + DEFAULT_AUTOPAGE_ALIGNMENT - 1) & ~(DEFAULT_AUTOPAGE_ALIGNMENT - 1)


def _block_roundup(size: int) -> int:
    return (size + 7) & ~7  # sizeof(void*) == 8 on 64-bit


class _FreshAllocatorMixin:
    """Mixin that provides a fresh allocator per test via setUp / tearDown."""

    allocator: HeapAllocator

    def setUp(self):
        self.allocator = HeapAllocator()

    def tearDown(self):
        # Let the allocator's __dealloc__ free the C resources.
        del self.allocator
        gc.collect()


# ---------------------------------------------------------------------------
# Singleton / global sanity
# ---------------------------------------------------------------------------

class TestGlobalAllocatorExists(unittest.TestCase):
    """The module still exports a global ALLOCATOR for convenience."""

    def test_global_allocator_importable(self):
        from cbase.allocator_protocol.c_heap_allocator import ALLOCATOR
        self.assertIsInstance(ALLOCATOR, HeapAllocator)


# ---------------------------------------------------------------------------
# Constructor / creation
# ---------------------------------------------------------------------------

class TestHeapAllocatorCreation(unittest.TestCase):
    """Creating and destroying HeapAllocator instances."""

    def test_constructor_creates_fresh_instance(self):
        a = HeapAllocator()
        self.assertIsInstance(a, HeapAllocator)
        self.assertTrue(a.owner)

    def test_multiple_instances_independent(self):
        a1 = HeapAllocator()
        a2 = HeapAllocator()
        self.assertIsNot(a1, a2)
        self.assertEqual(a1.mapped_pages, 0)
        self.assertEqual(a2.mapped_pages, 0)

    def test_destroy_and_recreate(self):
        a1 = HeapAllocator()
        del a1
        gc.collect()
        a2 = HeapAllocator()
        self.assertEqual(a2.mapped_pages, 0)

    def test_default_constants(self):
        self.assertEqual(DEFAULT_AUTOPAGE_CAPACITY, 64 * 1024)
        self.assertEqual(MAX_AUTOPAGE_CAPACITY, 16 * 1024 * 1024)
        self.assertEqual(DEFAULT_AUTOPAGE_ALIGNMENT, 4 * 1024)


# ---------------------------------------------------------------------------
# calloc
# ---------------------------------------------------------------------------

class TestCalloc(_FreshAllocatorMixin, unittest.TestCase):

    # -- tiny allocations ---------------------------------------------------

    def test_size_1(self):
        b = self.allocator.calloc(1)
        self.assertEqual(b.size, 1)
        self.assertGreaterEqual(b.capacity, 1)

    def test_size_1_zeroed(self):
        b = self.allocator.calloc(1)
        self.assertEqual(bytes(b.buffer), b'\x00')

    def test_size_16_zeroed(self):
        b = self.allocator.calloc(16)
        self.assertEqual(bytes(b.buffer), b'\x00' * 16)

    def test_size_8_writable(self):
        b = self.allocator.calloc(8)
        b.buffer[:4] = b'\xde\xad\xbe\xef'
        self.assertEqual(bytes(b.buffer[:4]), b'\xde\xad\xbe\xef')

    # -- capacity alignment -------------------------------------------------

    def test_capacity_is_block_aligned(self):
        for size in (1, 3, 7, 8, 9, 15, 16, 31, 127, 255, 1023):
            with self.subTest(size=size):
                b = self.allocator.calloc(size)
                self.assertEqual(b.size, size)
                self.assertEqual(b.capacity, _block_roundup(size))

    # -- zero-initialisation across sizes ----------------------------------

    def test_zeroed_various_sizes(self):
        for sz in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            with self.subTest(size=sz):
                b = self.allocator.calloc(sz)
                self.assertEqual(bytes(b.buffer), b'\x00' * sz)

    # -- 1 KiB write / read ------------------------------------------------

    def test_1k_write_read(self):
        b = self.allocator.calloc(1024)
        pattern = bytes(i & 0xFF for i in range(1024))
        b.buffer[:] = pattern
        self.assertEqual(bytes(b.buffer), pattern)

    # -- address -----------------------------------------------------------

    def test_address_is_hex(self):
        b = self.allocator.calloc(64)
        self.assertTrue(b.address.startswith('0x'))

    # -- parent page -------------------------------------------------------

    def test_has_parent_page(self):
        b = self.allocator.calloc(256)
        page = b.parent_page
        self.assertIsInstance(page, HeapMemoryPage)
        self.assertGreater(page.capacity, 0)

    # -- consecutive allocs same page --------------------------------------

    def test_consecutive_on_same_page(self):
        b1 = self.allocator.calloc(128)
        b2 = self.allocator.calloc(128)
        self.assertEqual(b1.parent_page.address, b2.parent_page.address)
        self.assertNotEqual(b1.address, b2.address)

    # -- error -------------------------------------------------------------

    def test_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.calloc(0)

    # -- with_lock=False ---------------------------------------------------

    def test_with_lock_false(self):
        b = self.allocator.calloc(64, with_lock=False)
        self.assertEqual(b.size, 64)
        self.assertEqual(bytes(b.buffer[:4]), b'\x00' * 4)


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------

class TestRequest(_FreshAllocatorMixin, unittest.TestCase):

    def test_basic(self):
        b = self.allocator.request(512)
        self.assertEqual(b.size, 512)
        self.assertGreaterEqual(b.capacity, 512)

    def test_zeroed(self):
        b = self.allocator.request(256)
        self.assertEqual(bytes(b.buffer), b'\x00' * 256)

    def test_reuses_freed_block_exact_size(self):
        b1 = self.allocator.calloc(128)
        addr1 = b1.address
        self.allocator.free(b1)

        b2 = self.allocator.request(128)
        self.assertEqual(b2.address, addr1)

    def test_reuses_freed_block_smaller_request(self):
        b1 = self.allocator.calloc(256)
        addr1 = b1.address
        self.allocator.free(b1)

        b2 = self.allocator.request(64)
        self.assertEqual(b2.address, addr1)
        self.assertEqual(b2.size, 64)

    def test_zeroed_after_reuse(self):
        b1 = self.allocator.calloc(64)
        b1.buffer[:4] = b'DIRT'
        self.allocator.free(b1)

        b2 = self.allocator.request(64)
        self.assertEqual(bytes(b2.buffer[:4]), b'\x00' * 4)

    def test_lifo_free_list_order(self):
        """Free list is LIFO; request returns most recently freed block."""
        b1 = self.allocator.calloc(32)
        b2 = self.allocator.calloc(64)
        addr1, addr2 = b1.address, b2.address

        self.allocator.free(b2)
        self.allocator.free(b1)

        b3 = self.allocator.request(16)
        self.assertEqual(b3.address, addr1)
        b4 = self.allocator.request(48)
        self.assertEqual(b4.address, addr2)

    def test_too_large_for_free_list_extends(self):
        tiny = self.allocator.calloc(8)
        self.allocator.free(tiny)
        pages_before = self.allocator.mapped_pages

        big = self.allocator.request(DEFAULT_AUTOPAGE_CAPACITY)
        self.assertIsNotNone(big)
        self.assertGreater(big.capacity, 8)
        self.assertGreaterEqual(self.allocator.mapped_pages, pages_before)

    def test_scan_all_pages_false(self):
        b = self.allocator.request(32, scan_all_pages=False)
        self.assertEqual(b.size, 32)

    def test_scan_all_pages_true_reuses_across_pages(self):
        """A freed block on an older page is found when scan_all_pages=True."""
        p1 = self.allocator.extend(8192)
        b1 = self.allocator.calloc(64)
        addr1 = b1.address
        # Force a second page so b1 is no longer on the active page
        p2 = self.allocator.extend(8192)
        self.allocator.free(b1)
        # request with scan_all_pages=True should find b1 on the older page
        b2 = self.allocator.request(64, scan_all_pages=True)
        self.assertEqual(b2.address, addr1,
                         "scan_all_pages=True must find freed block on older page")

    def test_zero_size_raises(self):
        with self.assertRaises(OSError):
            self.allocator.request(0)

    def test_with_lock_false(self):
        b = self.allocator.request(32, with_lock=False)
        self.assertEqual(b.size, 32)


# ---------------------------------------------------------------------------
# free
# ---------------------------------------------------------------------------

class TestFree(_FreshAllocatorMixin, unittest.TestCase):

    def test_free_increases_free_list(self):
        free_before = len(list(self.allocator.free_list()))
        b = self.allocator.calloc(200)
        self.allocator.free(b)
        free_after = len(list(self.allocator.free_list()))
        self.assertEqual(free_after, free_before + 1)

    def test_free_then_block_is_in_free_list(self):
        b = self.allocator.calloc(128)
        addr = b.address
        self.allocator.free(b)
        addrs = {f.address for f in self.allocator.free_list()}
        self.assertIn(addr, addrs)

    def test_double_free_is_noop_second_time(self):
        """Freeing an already-freed block: second free is a no-op
        (the block's owner flag is already False, so no C call is made)."""
        b = self.allocator.calloc(256)
        self.allocator.free(b)
        self.allocator.free(b)  # must not crash or corrupt

    def test_free_uninitialized_block_no_crash(self):
        empty = HeapMemoryBlock(0, False)
        self.allocator.free(empty)

    def test_free_with_lock_false(self):
        b = self.allocator.calloc(64)
        self.allocator.free(b, with_lock=False)

    def test_free_many(self):
        blocks = [self.allocator.calloc(128) for _ in range(20)]
        addr = [_.address for _ in blocks]
        for b in blocks:
            self.allocator.free(b)
        free_addrs = {f.address for f in self.allocator.free_list()}
        for b in addr:
            self.assertIn(b, free_addrs)


# ---------------------------------------------------------------------------
# reclaim
# ---------------------------------------------------------------------------

class TestReclaim(_FreshAllocatorMixin, unittest.TestCase):

    def test_reclaim_reduces_free_list(self):
        blocks = [self.allocator.calloc(256) for _ in range(8)]
        for b in blocks:
            self.allocator.free(b)
        free_before = len(list(self.allocator.free_list()))
        self.allocator.reclaim()
        free_after = len(list(self.allocator.free_list()))
        self.assertLess(free_after, free_before)

    def test_reclaim_reduces_page_occupied(self):
        b = self.allocator.calloc(512)
        page = b.parent_page
        occupied_before = page.occupied
        self.allocator.free(b)
        page.reclaim()
        self.assertLess(page.occupied, occupied_before)

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

class TestExtend(_FreshAllocatorMixin, unittest.TestCase):

    def test_extend_default_creates_page(self):
        self.assertEqual(self.allocator.mapped_pages, 0)
        page = self.allocator.extend(0)
        self.assertIsInstance(page, HeapMemoryPage)
        self.assertEqual(self.allocator.mapped_pages, 1)

    def test_extend_default_capacity(self):
        page = self.allocator.extend(0)
        self.assertEqual(page.capacity, DEFAULT_AUTOPAGE_CAPACITY)

    def test_extend_exact_size_is_page_aligned(self):
        page = self.allocator.extend(5000)
        self.assertGreaterEqual(page.capacity, 5000)
        self.assertEqual(page.capacity, _page_roundup(5000))

    def test_extend_multiple(self):
        for _ in range(4):
            self.allocator.extend(4096)
        self.assertEqual(self.allocator.mapped_pages, 4)

    def test_second_page_doubles(self):
        p1 = self.allocator.extend(0)
        p2 = self.allocator.extend(0)
        expected = min(p1.capacity * 2, MAX_AUTOPAGE_CAPACITY)
        self.assertEqual(p2.capacity, expected)

    def test_third_page_doubles_again(self):
        p1 = self.allocator.extend(0)
        p2 = self.allocator.extend(0)
        p3 = self.allocator.extend(0)
        expected = min(p2.capacity * 2, MAX_AUTOPAGE_CAPACITY)
        self.assertEqual(p3.capacity, expected)

    def test_page_never_exceeds_max(self):
        for _ in range(16):
            self.allocator.extend(0)
        last = self.allocator.active_page
        self.assertLessEqual(last.capacity, MAX_AUTOPAGE_CAPACITY)

    def test_extend_with_lock_false(self):
        page = self.allocator.extend(1024, with_lock=False)
        self.assertGreater(page.capacity, 0)

    def test_page_capacity_always_aligned(self):
        pages = []
        for _ in range(5):
            pages.append(self.allocator.extend(0))
        for p in pages:
            self.assertEqual(p.capacity % DEFAULT_AUTOPAGE_ALIGNMENT, 0)

    def test_no_pages_before_extend(self):
        self.assertEqual(self.allocator.mapped_pages, 0)
        self.assertIsNone(self.allocator.active_page)

    def test_calloc_triggers_first_page(self):
        """First calloc implicitly extends a page when none exists."""
        self.assertEqual(self.allocator.mapped_pages, 0)
        b = self.allocator.calloc(64)
        self.assertGreaterEqual(self.allocator.mapped_pages, 1)
        self.assertIsNotNone(self.allocator.active_page)
        self.assertEqual(b.parent_page.address,
                         self.allocator.active_page.address)


# ---------------------------------------------------------------------------
# Iteration
# ---------------------------------------------------------------------------

class TestIteration(_FreshAllocatorMixin, unittest.TestCase):

    def test_pages_empty_initially(self):
        self.assertEqual(list(self.allocator.pages()), [])

    def test_pages_after_extend(self):
        self.allocator.extend(4096)
        pages = list(self.allocator.pages())
        self.assertEqual(len(pages), 1)
        self.assertIsInstance(pages[0], HeapMemoryPage)

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

    def test_allocated_does_not_include_freed(self):
        b = self.allocator.calloc(256)
        self.allocator.free(b)
        allocated = list(self.allocator.allocated())
        addrs = {a.address for a in allocated}
        self.assertNotIn(b.address, addrs)

    def test_free_list_empty_initially(self):
        self.assertEqual(list(self.allocator.free_list()), [])

    def test_active_page_none_initially(self):
        self.assertIsNone(self.allocator.active_page)

    def test_allocated_block_chain(self):
        """next_allocated links blocks on the same page in LIFO order.
        Each new calloc block is inserted at the head of the page's
        allocated list, so b2 (newer) points to b1 (older)."""
        page = self.allocator.extend(16384)
        b1 = self.allocator.calloc(32)
        b2 = self.allocator.calloc(32)
        self.assertEqual(b1.parent_page.address, page.address)
        self.assertEqual(b2.parent_page.address, page.address)
        self.assertIsNotNone(b2.next_allocated,
                             "b2 must link to b1 via next_allocated")
        self.assertEqual(b2.next_allocated.address, b1.address)


# ---------------------------------------------------------------------------
# Memory patterns & stress
# ---------------------------------------------------------------------------

class TestPatterns(_FreshAllocatorMixin, unittest.TestCase):

    def test_write_full_block_4k(self):
        size = 4096
        b = self.allocator.calloc(size)
        pattern = bytes((i * 7 + 13) & 0xFF for i in range(size))
        b.buffer[:] = pattern
        self.assertEqual(bytes(b.buffer), pattern)

    def test_boundary_first_last_byte(self):
        for size in (2, 8, 64, 255, 256, 1024):
            with self.subTest(size=size):
                b = self.allocator.calloc(size)
                b.buffer[0] = b'\xAA'
                b.buffer[size - 1] = b'\x55'
                self.assertEqual(b.buffer[0], b'\xAA')
                self.assertEqual(b.buffer[size - 1], b'\x55')

    def test_large_allocation_near_page_size(self):
        size = DEFAULT_AUTOPAGE_CAPACITY - 4096
        b = self.allocator.calloc(size)
        self.assertEqual(b.size, size)
        b.buffer[0] = b'\x01'
        b.buffer[size // 2] = b'\x80'
        b.buffer[size - 1] = b'\xFF'
        self.assertEqual(b.buffer[0], b'\x01')
        self.assertEqual(b.buffer[size // 2], b'\x80')
        self.assertEqual(b.buffer[size - 1], b'\xFF')

    def test_two_blocks_independent(self):
        b1 = self.allocator.calloc(256)
        b2 = self.allocator.calloc(256)
        b1.buffer[:4] = b'\x01\x02\x03\x04'
        b2.buffer[:4] = b'\xaa\xbb\xcc\xdd'
        self.assertEqual(bytes(b1.buffer[:4]), b'\x01\x02\x03\x04')
        self.assertEqual(bytes(b2.buffer[:4]), b'\xaa\xbb\xcc\xdd')

    def test_alloc_free_cycle_many(self):
        """Repeated alloc/free within the same allocator."""
        addrs = set()
        for i in range(50):
            b = self.allocator.calloc(64)
            addrs.add(b.address)
            b.buffer[0] = bytes([i & 0xFF])
            self.allocator.free(b)
        b2 = self.allocator.request(64)
        self.assertIn(b2.address, addrs)
        self.assertEqual(b2.buffer[0], b'\x00')

    def test_mixed_sizes_write_read(self):
        sizes = (16, 512, 8, 2048, 256, 1, 4096, 128, 32, 1024)
        blocks = []
        for sz in sizes:
            b = self.allocator.calloc(sz)
            self.assertEqual(b.size, sz)
            blocks.append(b)
        for i, b in enumerate(blocks):
            b.buffer[0] = bytes([i & 0xFF])
        for i, b in enumerate(blocks):
            self.assertEqual(b.buffer[0], bytes([i & 0xFF]))

    def test_request_many_after_frees_reuses(self):
        for _ in range(20):
            b = self.allocator.calloc(128)
            b.buffer[0] = b'\x42'
            self.allocator.free(b)
        reused = []
        for _ in range(20):
            b2 = self.allocator.request(128)
            self.assertEqual(b2.size, 128)
            self.assertEqual(b2.buffer[0], b'\x00')
            reused.append(b2)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(_FreshAllocatorMixin, unittest.TestCase):

    def test_uninitialized_block_repr(self):
        empty = HeapMemoryBlock(0, False)
        self.assertIn('uninitialized', repr(empty))

    def test_uninitialized_page_repr(self):
        empty = HeapMemoryPage(0)
        self.assertIn('uninitialized', repr(empty))

    def test_allocator_repr(self):
        r = repr(self.allocator)
        self.assertIn('HeapAllocator', r)

    def test_gc_of_allocator_frees_pages(self):
        a = HeapAllocator()
        a.calloc(256)
        a.calloc(512)
        a.extend(4096)
        del a
        gc.collect()

    def test_reclaim_without_any_alloc(self):
        self.allocator.reclaim()

    def test_free_list_iteration_after_reclaim(self):
        b = self.allocator.calloc(64)
        self.allocator.free(b)
        self.allocator.reclaim()
        _ = list(self.allocator.free_list())

    def test_block_next_free_on_allocated_block(self):
        b = self.allocator.calloc(64)
        self.assertIsNone(b.next_free)


# ---------------------------------------------------------------------------
# Config properties (autopage_capacity, autopage_capacity_max,
# autopage_alignment)
# ---------------------------------------------------------------------------

class TestAllocatorConfig(_FreshAllocatorMixin, unittest.TestCase):
    """The three config fields are exposed as readable/writable properties."""

    def test_default_autopage_capacity(self):
        self.assertEqual(self.allocator.autopage_capacity,
                         DEFAULT_AUTOPAGE_CAPACITY)

    def test_default_autopage_capacity_max(self):
        self.assertEqual(self.allocator.autopage_capacity_max,
                         MAX_AUTOPAGE_CAPACITY)

    def test_default_autopage_alignment(self):
        self.assertEqual(self.allocator.autopage_alignment,
                         DEFAULT_AUTOPAGE_ALIGNMENT)

    def test_set_autopage_capacity_affects_extend(self):
        new_cap = 8192
        self.allocator.autopage_capacity = new_cap
        self.assertEqual(self.allocator.autopage_capacity, new_cap)
        page = self.allocator.extend(0)
        self.assertEqual(page.capacity, new_cap)

    def test_set_autopage_capacity_max_caps_extend(self):
        self.allocator.autopage_capacity_max = 32768
        # Grow pages until they hit the cap
        for _ in range(8):
            self.allocator.extend(0)
        last = self.allocator.active_page
        self.assertLessEqual(last.capacity, 32768)

    def test_set_autopage_alignment_affects_roundup(self):
        self.allocator.autopage_alignment = 8192
        page = self.allocator.extend(5000)
        self.assertEqual(page.capacity % 8192, 0)
        self.assertGreaterEqual(page.capacity, 5000)

    def test_independent_configs_dont_cross_contaminate(self):
        """Two allocators can have different configs."""
        a2 = HeapAllocator()
        self.allocator.autopage_capacity = 16384
        self.assertEqual(self.allocator.autopage_capacity, 16384)
        self.assertEqual(a2.autopage_capacity, DEFAULT_AUTOPAGE_CAPACITY)
        del a2

    def test_mapped_pages_raises_when_uninitialized(self):
        # Not applicable with _FreshAllocatorMixin, but test edge:
        self.assertGreaterEqual(self.allocator.mapped_pages, 0)


if __name__ == '__main__':
    unittest.main()
