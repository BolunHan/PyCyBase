"""Tests for the size-binned free lists (c_heap_allocator bins).

Covers the corner cases of the bin design: exact-bin reuse, LIFO order,
cross-bin isolation, pow2-class bins, the stranding regression (a large
block must be reusable after a deluge of small frees), zeroing, size
preservation across reuse, page-path behavior and reclaim.

NOTE: every `request()` wrapper owns its block — it auto-frees on GC.
Tests must hold wrappers in variables and free them explicitly.
"""
import gc
import unittest

from cbase.allocator_protocol.c_heap_allocator import HeapAllocator


class _FreshAllocatorMixin:
    """Fresh allocator per test so state does not leak between tests."""

    allocator: HeapAllocator

    def setUp(self):
        self.allocator = HeapAllocator()

    def tearDown(self):
        # GC lingering owner=True wrappers while the allocator is alive.
        gc.collect()
        del self.allocator
        gc.collect()


# ---------------------------------------------------------------------------
# Capacity / rounding
# ---------------------------------------------------------------------------

class TestBinCapacity(_FreshAllocatorMixin, unittest.TestCase):
    """Request sizes map to 8-byte-aligned capacities (bin keys)."""

    def test_minimum_size_rounds_to_8(self):
        for size in (1, 7):
            with self.subTest(size=size):
                block = self.allocator.request(size)
                self.assertEqual(block.capacity, 8)
                self.assertEqual(block.size, size)
                self.allocator.free(block)

    def test_odd_size_rounds_up(self):
        block = self.allocator.request(1001)
        self.assertEqual(block.capacity, 1008)
        self.assertEqual(block.size, 1001)
        self.allocator.free(block)

    def test_exact_bin_boundary(self):
        """65536 is the last exact bin; 65544 starts the pow2 classes."""
        small = self.allocator.request(65536)
        self.assertEqual(small.capacity, 65536)
        self.allocator.free(small)

        large = self.allocator.request(65544)
        self.assertEqual(large.capacity, 65544)
        self.allocator.free(large)


# ---------------------------------------------------------------------------
# Exact-bin reuse
# ---------------------------------------------------------------------------

class TestExactBinReuse(_FreshAllocatorMixin, unittest.TestCase):
    """Same-size reuse must be exact and O(1) (same bin, same address)."""

    def test_same_size_returns_same_pointer(self):
        first = self.allocator.request(64)
        addr = first.address
        self.allocator.free(first)
        second = self.allocator.request(64)
        try:
            self.assertEqual(second.address, addr)
        finally:
            self.allocator.free(second)

    def test_lifo_order_within_bin(self):
        a = self.allocator.request(64)
        b = self.allocator.request(64)
        c = self.allocator.request(64)
        a_addr, b_addr, c_addr = a.address, b.address, c.address
        self.allocator.free(a)
        self.allocator.free(b)
        self.allocator.free(c)

        # Most recently freed block is reused first.
        d = self.allocator.request(64)
        self.assertEqual(d.address, c_addr)
        e = self.allocator.request(64)
        self.assertEqual(e.address, b_addr)
        f = self.allocator.request(64)
        self.assertEqual(f.address, a_addr)

        self.allocator.free(d)
        self.allocator.free(e)
        self.allocator.free(f)

    def test_buffer_zeroed_on_reuse(self):
        block = self.allocator.request(64)
        addr = block.address
        block.buffer[:] = b"\xAB" * 64
        self.allocator.free(block)

        again = self.allocator.request(64)
        try:
            self.assertEqual(again.address, addr)
            self.assertEqual(bytes(again.buffer[:64]), b"\x00" * 64)
        finally:
            self.allocator.free(again)

    def test_size_field_preserved_on_reuse(self):
        """Pow2 in-bin first-fit: a reused block keeps its capacity but
        reports the new (smaller) request size."""
        big = self.allocator.request(80000)
        addr = big.address
        self.assertEqual(big.capacity, 80000)
        self.allocator.free(big)

        again = self.allocator.request(70000)
        try:
            self.assertEqual(again.address, addr)
            self.assertEqual(again.capacity, 80000)
            self.assertEqual(again.size, 70000)
        finally:
            self.allocator.free(again)


# ---------------------------------------------------------------------------
# Cross-bin isolation
# ---------------------------------------------------------------------------

class TestCrossBinIsolation(_FreshAllocatorMixin, unittest.TestCase):
    """A freed block must never satisfy a request of a different exact bin."""

    def test_small_free_not_reused_by_larger_request(self):
        small = self.allocator.request(64)
        small_addr = small.address
        self.allocator.free(small)

        larger = self.allocator.request(128)
        try:
            self.assertNotEqual(larger.address, small_addr)
            self.assertEqual(larger.capacity, 128)
        finally:
            self.allocator.free(larger)

        # The 64-block is still available for a 64-request.
        again = self.allocator.request(64)
        self.assertEqual(again.address, small_addr)
        self.allocator.free(again)

    def test_bin_boundary_isolation(self):
        """65536 and 65544 must not cross-reuse (exact vs pow2 class)."""
        exact = self.allocator.request(65536)
        exact_addr = exact.address
        self.allocator.free(exact)

        pow2 = self.allocator.request(65544)
        try:
            self.assertNotEqual(pow2.address, exact_addr)
        finally:
            self.allocator.free(pow2)

        again = self.allocator.request(65536)
        self.assertEqual(again.address, exact_addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Exact-bin probe (AP_HEAP_EXACT_BIN_PROBE_COUNT, default 2)
# ---------------------------------------------------------------------------

class TestExactBinProbe(_FreshAllocatorMixin, unittest.TestCase):
    """On an exact-bin miss, up to PROBE_COUNT larger exact bins are
    probed; a taken larger block returns to its own bin on free."""

    def test_probe_uses_slightly_larger_block(self):
        big = self.allocator.request(72)   # capacity 72 -> bin 9
        addr = big.address
        self.allocator.free(big)

        small = self.allocator.request(64)  # bin 8 miss -> probes 9, 10
        try:
            self.assertEqual(small.address, addr)
            self.assertEqual(small.capacity, 72)
            self.assertEqual(small.size, 64)
        finally:
            self.allocator.free(small)

    def test_probe_stops_at_probe_count(self):
        """A block beyond the probe range is not taken (bin 12 vs probe
        range 9-10 from a 64-request)."""
        far = self.allocator.request(96)   # capacity 96 -> bin 12
        far_addr = far.address
        self.allocator.free(far)

        small = self.allocator.request(64)
        try:
            self.assertNotEqual(small.address, far_addr)
        finally:
            self.allocator.free(small)

        again = self.allocator.request(96)
        self.assertEqual(again.address, far_addr)
        self.allocator.free(again)

    def test_probed_block_recycles_to_own_bin(self):
        """A block taken by a smaller request returns to ITS bin on free."""
        big = self.allocator.request(72)
        big_addr = big.address
        self.allocator.free(big)

        small = self.allocator.request(64)
        self.assertEqual(small.address, big_addr)
        self.allocator.free(small)

        # The 72-capacity block is available to a 72-request again.
        again = self.allocator.request(72)
        self.assertEqual(again.address, big_addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Pow2-class bins (capacity > 64 KiB)
# ---------------------------------------------------------------------------

class TestPow2Bins(_FreshAllocatorMixin, unittest.TestCase):
    """Pow2-class bins reuse same-shape blocks and fit larger blocks."""

    def test_same_size_reuse(self):
        block = self.allocator.request(70000)
        addr = block.address
        self.allocator.free(block)
        again = self.allocator.request(70000)
        self.assertEqual(again.address, addr)
        self.allocator.free(again)

    def test_in_bin_first_fit_uses_larger_block(self):
        """A 70k request may take a freed 80k block from the same class."""
        big = self.allocator.request(80000)
        big_addr = big.address
        self.allocator.free(big)

        smaller = self.allocator.request(70000)
        try:
            self.assertEqual(smaller.address, big_addr)
        finally:
            self.allocator.free(smaller)

    def test_stranding_regression(self):
        """A large block freed BEFORE a small-block deluge must still be
        reusable afterwards (bins by size; the old bounded-probe design
        stranded it below the probe window)."""
        big = self.allocator.request(80000)
        big_addr = big.address
        self.allocator.free(big)

        for _ in range(65):
            tmp = self.allocator.request(64)
            self.allocator.free(tmp)

        again = self.allocator.request(80000)
        self.assertEqual(again.address, big_addr)
        self.allocator.free(again)

    def test_overflow_class_reuse(self):
        """Allocations beyond the largest pow2 class share the overflow bin."""
        block = self.allocator.request(20 * 1024 * 1024)
        addr = block.address
        self.assertGreater(block.capacity, 16 * 1024 * 1024)
        self.allocator.free(block)
        again = self.allocator.request(20 * 1024 * 1024)
        self.assertEqual(again.address, addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Steady-state / page growth
# ---------------------------------------------------------------------------

class TestSteadyState(_FreshAllocatorMixin, unittest.TestCase):
    """Same-shape churn must not grow the allocator (full bin reuse)."""

    def test_churn_does_not_grow_pages(self):
        # Warm up: first allocations carve pages.
        for _ in range(1000):
            b = self.allocator.request(88)
            self.allocator.free(b)
        pages_before = self.allocator.mapped_pages

        for _ in range(20000):
            b = self.allocator.request(88)
            self.allocator.free(b)

        self.assertEqual(self.allocator.mapped_pages, pages_before)

    def test_free_list_is_bounded_under_churn(self):
        """Mixed churn keeps the free list short (bins, no accumulation)."""
        for i in range(5000):
            b = self.allocator.request(64 if i % 2 else 128)
            self.allocator.free(b)
        n_free = sum(1 for _ in self.allocator.free_list())
        self.assertLess(n_free, 64)


# ---------------------------------------------------------------------------
# Reclaim
# ---------------------------------------------------------------------------

class TestReclaim(_FreshAllocatorMixin, unittest.TestCase):
    """Page reclaim removes fully-freed blocks from pages and bins."""

    def test_reclaim_frees_whole_page(self):
        blocks = [self.allocator.request(64) for _ in range(1000)]
        for b in blocks:
            self.allocator.free(b)

        for page in self.allocator.pages():
            page.reclaim()

        # Reclaimed blocks must leave the free list entirely.
        n_free = sum(1 for _ in self.allocator.free_list())
        self.assertEqual(n_free, 0)
        for page in self.allocator.pages():
            self.assertEqual(page.occupied, 40)  # page-header overhead only


if __name__ == "__main__":
    unittest.main()
