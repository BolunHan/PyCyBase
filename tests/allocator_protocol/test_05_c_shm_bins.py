"""Tests for the size-binned free lists in the SHM allocator.

Mirrors the heap bin corner cases (test_04) against the shared-memory
allocator: exact-bin reuse, LIFO order, cross-bin isolation, pow2-class
reuse, the stranding regression, and steady-state page growth.

NOTE: every `request()` wrapper owns its block and auto-frees on GC.
A wrapper deallocating AFTER the allocator's segments are unmapped
segfaults, so every wrapper must be freed explicitly (try/finally).
"""
import gc
import unittest

from cbase.allocator_protocol.c_shm_allocator import (
    SharedMemoryAllocator,
)


class _FreshAllocatorMixin:
    """Fresh SHM allocator per test; teardown cleans the segments."""

    allocator: SharedMemoryAllocator

    def setUp(self):
        self.allocator = SharedMemoryAllocator()

    def tearDown(self):
        # Free any lingering owner=True wrappers while segments are mapped.
        gc.collect()
        del self.allocator
        gc.collect()


# ---------------------------------------------------------------------------
# Exact-bin reuse
# ---------------------------------------------------------------------------

class TestShmExactBinReuse(_FreshAllocatorMixin, unittest.TestCase):
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


# ---------------------------------------------------------------------------
# Cross-bin isolation
# ---------------------------------------------------------------------------

class TestShmCrossBinIsolation(_FreshAllocatorMixin, unittest.TestCase):
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

        again = self.allocator.request(64)
        self.assertEqual(again.address, small_addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Exact-bin probe (AP_SHM_EXACT_BIN_PROBE_COUNT, default 2)
# ---------------------------------------------------------------------------

class TestShmExactBinProbe(_FreshAllocatorMixin, unittest.TestCase):
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
        big = self.allocator.request(72)
        big_addr = big.address
        self.allocator.free(big)

        small = self.allocator.request(64)
        self.assertEqual(small.address, big_addr)
        self.allocator.free(small)

        again = self.allocator.request(72)
        self.assertEqual(again.address, big_addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Pow2-class bins
# ---------------------------------------------------------------------------

class TestShmPow2Bins(_FreshAllocatorMixin, unittest.TestCase):
    def test_same_size_reuse(self):
        block = self.allocator.request(70000)
        addr = block.address
        self.allocator.free(block)
        again = self.allocator.request(70000)
        self.assertEqual(again.address, addr)
        self.allocator.free(again)

    def test_in_bin_first_fit_uses_larger_block(self):
        big = self.allocator.request(80000)
        big_addr = big.address
        self.allocator.free(big)
        smaller = self.allocator.request(70000)
        try:
            self.assertEqual(smaller.address, big_addr)
        finally:
            self.allocator.free(smaller)

    def test_stranding_regression(self):
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
        block = self.allocator.request(20 * 1024 * 1024)
        addr = block.address
        self.allocator.free(block)
        again = self.allocator.request(20 * 1024 * 1024)
        self.assertEqual(again.address, addr)
        self.allocator.free(again)


# ---------------------------------------------------------------------------
# Steady state
# ---------------------------------------------------------------------------

class TestShmSteadyState(_FreshAllocatorMixin, unittest.TestCase):
    def test_churn_does_not_grow_pages(self):
        for _ in range(1000):
            b = self.allocator.request(88)
            self.allocator.free(b)
        pages_before = self.allocator.mapped_pages

        for _ in range(20000):
            b = self.allocator.request(88)
            self.allocator.free(b)

        self.assertEqual(self.allocator.mapped_pages, pages_before)


if __name__ == "__main__":
    unittest.main()
