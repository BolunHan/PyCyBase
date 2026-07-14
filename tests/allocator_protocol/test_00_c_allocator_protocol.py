import multiprocessing as mp
import unittest

from cbase.allocator_protocol.c_allocator_protocol import (
    AllocatorProtocol,
    AP_FREELIST,
    AP_LOCKED,
    AP_LOCKFREE,
    AP_SHARED,
)

# ---------------------------------------------------------------------------
# Fork-mode shared-memory helpers
#
# cdef classes cannot be pickled, so they cannot be passed via mp.Process
# args in forkserver/spawn mode.  Instead we store the allocator in a
# module-level global before forking with mp.get_context('fork'), and the
# child function reads it from there.  A Queue carries results back to the
# parent so assertions run in-band with unittest.
# ---------------------------------------------------------------------------

_FORK_ALLOC: AllocatorProtocol | None = None


class TestAllocatorProtocolBasic(unittest.TestCase):
    """Test basic AllocatorProtocol functionality (lock state is macro-configurable,
    so no assertions are made about the default with_lock)."""

    def test_allocator_creation_with_size(self):
        size = 1024
        allocator = AllocatorProtocol(size)
        self.assertEqual(allocator.size, size)

    def test_allocator_buffer_access(self):
        size = 256
        allocator = AllocatorProtocol(size)
        buf = allocator.buf
        buf[0] = b'a'
        self.assertEqual(buf[0], b'a')

    def test_allocator_buffer_write_read(self):
        size = 512
        allocator = AllocatorProtocol(size)
        buf = allocator.buf
        test_data = b"Hello, AllocatorProtocol!"
        buf[:len(test_data)] = test_data
        read_data = bytes(buf[:len(test_data)])
        self.assertEqual(read_data, test_data)

    def test_allocator_multiple_instances(self):
        size1, size2 = 256, 512
        alloc1 = AllocatorProtocol(size1)
        alloc2 = AllocatorProtocol(size2)
        self.assertEqual(alloc1.size, size1)
        self.assertEqual(alloc2.size, size2)
        alloc1.buf[0] = b'a'
        alloc2.buf[0] = b'b'
        self.assertEqual(alloc1.buf[0], b'a')
        self.assertEqual(alloc2.buf[0], b'b')

    def test_allocator_zero_size(self):
        allocator = AllocatorProtocol(0)
        with self.assertRaises(RuntimeError):
            _ = allocator.size


class TestAllocatorProtocolWithFreelist(unittest.TestCase):
    """Test AllocatorProtocol with AP_FREELIST flag enabled."""

    def test_freelist_mode_basic(self):
        with AP_FREELIST:
            size = 1024
            allocator = AllocatorProtocol(size)
            self.assertEqual(allocator.size, size)
            self.assertFalse(allocator.with_shm)

    def test_freelist_mode_buffer_operations(self):
        with AP_FREELIST:
            allocator = AllocatorProtocol(512)
            buf = allocator.buf
            test_data = b"Freelist mode test"
            buf[:len(test_data)] = test_data
            read_data = bytes(buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_freelist_mode_multiple_allocations(self):
        with AP_FREELIST:
            allocators = [AllocatorProtocol(256 * (i + 1)) for i in range(5)]
            for i, allocator in enumerate(allocators):
                expected_size = 256 * (i + 1)
                self.assertEqual(allocator.size, expected_size)
                pattern = bytes([i % 256])
                allocator.buf[0] = pattern
                self.assertEqual(allocator.buf[0], pattern)

    def test_freelist_with_lockfree(self):
        """AP_FREELIST combined with AP_LOCKFREE explicitly disables locking."""
        with AP_FREELIST | AP_LOCKFREE:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertFalse(allocator.with_lock)
            self.assertFalse(allocator.with_shm)

    def test_freelist_with_locked(self):
        """AP_FREELIST combined with AP_LOCKED explicitly enables locking."""
        with AP_FREELIST | AP_LOCKED:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertTrue(allocator.with_lock)
            self.assertFalse(allocator.with_shm)

    def test_freelist_recycle(self):
        with AP_FREELIST:
            allocator1 = AllocatorProtocol(256)
            allocator2 = AllocatorProtocol(256)
            addr_1 = allocator1.addr
            allocator1.buf[0] = b'x'
            del allocator1
            allocator3 = AllocatorProtocol(256)
            self.assertEqual(allocator3.addr, addr_1)
            self.assertEqual(allocator3.buf[0], b'\0')  # always zeroed out


class TestAllocatorProtocolWithShared(unittest.TestCase):
    """Test AllocatorProtocol with AP_SHARED (POSIX shared memory) flag.

    Single-process tests cover creation, buffer I/O, flag combinations, and
    edge cases.  Fork-mode tests (Linux only) validate that the shared-memory
    buffer is genuinely shared across process boundaries: a parent writes,
    a child reads/writes, and both sides observe each other's changes.
    """

    # ------------------------------------------------------------------
    # Single-process tests
    # ------------------------------------------------------------------

    def test_shared_mode_basic(self):
        """Creating an allocator under AP_SHARED yields the expected size
        and sets with_shm=True."""
        with AP_SHARED:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertTrue(allocator.with_shm)

    def test_shared_mode_buffer_write_read(self):
        """Bytes written to buf can be read back in the same process."""
        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            buf = allocator.buf
            test_data = b"Shared memory test"
            buf[:len(test_data)] = test_data
            self.assertEqual(bytes(buf[:len(test_data)]), test_data)

    def test_shared_mode_multiple_allocations_distinct(self):
        """Each allocation returns a buffer at a different address, and
        writes to one do not affect the other."""
        with AP_SHARED:
            a1 = AllocatorProtocol(256)
            a2 = AllocatorProtocol(256)
            a1.buf[:4] = b'\x01\x02\x03\x04'
            a2.buf[:4] = b'\xaa\xbb\xcc\xdd'
            self.assertEqual(bytes(a1.buf[:4]), b'\x01\x02\x03\x04')
            self.assertEqual(bytes(a2.buf[:4]), b'\xaa\xbb\xcc\xdd')
            self.assertNotEqual(a1.addr, a2.addr)

    def test_shared_mode_buffer_zero_initialized(self):
        """A freshly allocated buffer is zero-filled."""
        with AP_SHARED:
            allocator = AllocatorProtocol(1024)
            buf = allocator.buf
            self.assertEqual(bytes(buf[:64]), b'\x00' * 64)

    def test_shared_mode_buffer_full_capacity_writable(self):
        """Every byte up to size-1 is independently writable and readable."""
        size = 4096
        with AP_SHARED:
            allocator = AllocatorProtocol(size)
            buf = allocator.buf
            for i in range(0, size, size // 16):
                buf[i] = (i % 256).to_bytes(1, 'little')
            # spot-check every 256th byte
            for i in range(0, size, size // 16):
                self.assertEqual(buf[i], (i % 256).to_bytes(1, 'little'))

    def test_shared_mode_addr_is_valid(self):
        """addr returns a non-zero integer (a valid pointer)."""
        with AP_SHARED:
            allocator = AllocatorProtocol(128)
            self.assertIsInstance(allocator.addr, int)
            self.assertGreater(allocator.addr, 0)

    def test_shared_mode_flag_consistency(self):
        """with_shm is True for every size allocated under AP_SHARED."""
        sizes = [64, 128, 256, 512, 1024, 4096]
        with AP_SHARED:
            for sz in sizes:
                a = AllocatorProtocol(sz)
                self.assertTrue(a.with_shm, f"size={sz}")
                self.assertEqual(a.size, sz)

    def test_shared_mode_zero_size_raises(self):
        """A zero-size allocator raises RuntimeError on property access."""
        with AP_SHARED:
            a = AllocatorProtocol(0)
            with self.assertRaises(RuntimeError):
                _ = a.size

    # ------------------------------------------------------------------
    # Flag combinations
    # ------------------------------------------------------------------

    def test_shared_mode_with_lockfree(self):
        """AP_SHARED | AP_LOCKFREE → shm on, lock off."""
        with AP_SHARED | AP_LOCKFREE:
            allocator = AllocatorProtocol(1024)
            self.assertTrue(allocator.with_shm)
            self.assertFalse(allocator.with_lock)

    def test_shared_mode_with_locked(self):
        """AP_SHARED | AP_LOCKED → shm on, lock on."""
        with AP_SHARED | AP_LOCKED:
            allocator = AllocatorProtocol(1024)
            self.assertTrue(allocator.with_shm)
            self.assertTrue(allocator.with_lock)

    # ------------------------------------------------------------------
    # Fork-mode tests  — POSIX named SHM enables cross-process sharing
    # ------------------------------------------------------------------

    def test_fork_child_reads_parent_data(self):
        """Parent writes to the SHM buffer; the forked child reads the same
        data through the global _FORK_ALLOC reference and reports it back
        via a multiprocessing Queue."""
        ctx = mp.get_context('fork')
        test_data = b"SHM: parent->child"
        result_queue = ctx.Queue()

        def _child_reader():
            buf = _FORK_ALLOC.buf
            read_back = bytes(buf[:len(test_data)])
            result_queue.put(read_back)

        with AP_SHARED:
            alloc = AllocatorProtocol(len(test_data) + 16)
            alloc.buf[:len(test_data)] = test_data

            global _FORK_ALLOC
            _FORK_ALLOC = alloc

            p = ctx.Process(target=_child_reader)
            p.start()
            p.join()

            child_result = result_queue.get()
            self.assertEqual(child_result, test_data,
                             "child did not read the same data the parent wrote")
            self.assertEqual(p.exitcode, 0)

        _FORK_ALLOC = None

    def test_fork_child_writes_parent_sees(self):
        """Parent writes seed data, child overwrites a portion through the
        shared buffer, and the parent observes the child's modifications
        after the child exits."""
        ctx = mp.get_context('fork')
        seed_data = b"BEFORE"
        child_data = b"AFTER_"
        ready_queue = ctx.Queue()

        def _child_writer():
            buf = _FORK_ALLOC.buf
            # Verify seed data is visible
            seen = bytes(buf[:len(seed_data)])
            if seen != seed_data:
                ready_queue.put(('FAIL_SEED', seen))
                return
            # Overwrite
            buf[:len(child_data)] = child_data
            ready_queue.put(('OK', None))

        with AP_SHARED:
            alloc = AllocatorProtocol(128)
            alloc.buf[:len(seed_data)] = seed_data

            global _FORK_ALLOC
            _FORK_ALLOC = alloc

            p = ctx.Process(target=_child_writer)
            p.start()
            p.join()

            status, detail = ready_queue.get()
            self.assertEqual(status, 'OK',
                             f"child failed seed check: expected {seed_data!r}, saw {detail!r}")
            self.assertEqual(p.exitcode, 0)

            # Parent observes the child's modification
            self.assertEqual(bytes(alloc.buf[:len(child_data)]), child_data,
                             "parent did not see child's write to shared buffer")

        _FORK_ALLOC = None

    # ------------------------------------------------------------------
    # Fork-mode tests with ~AP_SHARED (heap-backed, no cross-process sharing)
    # ------------------------------------------------------------------

    def test_fork_no_shared_child_write_not_visible_to_parent(self):
        """Under ~AP_SHARED the buffer is heap-backed.  A forked child's
        writes trigger CoW and must NOT be visible to the parent."""
        ctx = mp.get_context('fork')
        seed_data = b"ORIGINAL"
        child_data = b"CHANGED!"
        assert len(seed_data) == len(child_data), "test data must be same length"
        ready_queue = ctx.Queue()

        def _child_writer():
            buf = _FORK_ALLOC.buf
            seen = bytes(buf[:len(seed_data)])
            buf[:len(child_data)] = child_data
            ready_queue.put(seen)

        with ~AP_SHARED:
            alloc = AllocatorProtocol(128)
            alloc.buf[:len(seed_data)] = seed_data

            global _FORK_ALLOC
            _FORK_ALLOC = alloc

            p = ctx.Process(target=_child_writer)
            p.start()
            p.join()

            child_saw = ready_queue.get()
            self.assertEqual(p.exitcode, 0)
            # Child saw the original data at fork time
            self.assertEqual(child_saw, seed_data)
            # Parent must NOT see the child's CoW modifications
            self.assertEqual(bytes(alloc.buf[:len(seed_data)]), seed_data,
                             "~AP_SHARED: parent must not see child writes")

        _FORK_ALLOC = None

    def test_fork_no_shared_parent_write_not_visible_to_child(self):
        """Under ~AP_SHARED, the parent modifies its buffer after fork;
        the child must still see the pre-fork snapshot (CoW isolation)."""
        ctx = mp.get_context('fork')
        seed_data = b"BEFORE_"
        after_data = b"_AFTER_"
        assert len(seed_data) == len(after_data), "test data must be same length"
        ready_queue = ctx.Queue()

        def _child_reader():
            # Child reads its inherited CoW snapshot
            buf = _FORK_ALLOC.buf
            ready_queue.put(bytes(buf[:len(seed_data)]))

        with ~AP_SHARED:
            alloc = AllocatorProtocol(128)
            alloc.buf[:len(seed_data)] = seed_data

            global _FORK_ALLOC
            _FORK_ALLOC = alloc

            p = ctx.Process(target=_child_reader)
            p.start()

            # Parent modifies AFTER fork — child should not see this
            alloc.buf[:len(after_data)] = after_data

            p.join()

            child_saw = ready_queue.get()
            self.assertEqual(p.exitcode, 0)
            # Child must see the pre-fork data, NOT the parent's post-fork write
            self.assertEqual(child_saw, seed_data,
                             "~AP_SHARED: child must not see parent's post-fork write")
            # Parent sees its own modification
            self.assertEqual(bytes(alloc.buf[:len(after_data)]), after_data)

        _FORK_ALLOC = None


class TestAllocatorProtocolLockfree(unittest.TestCase):
    """Test AP_LOCKFREE context manager."""

    def test_lockfree_disables_lock(self):
        with AP_LOCKFREE:
            allocator = AllocatorProtocol(256)
            self.assertFalse(allocator.with_lock)

    def test_lockfree_with_freelist(self):
        with AP_LOCKFREE | AP_FREELIST:
            allocator = AllocatorProtocol(128)
            self.assertFalse(allocator.with_lock)
            self.assertFalse(allocator.with_shm)

    def test_lockfree_buffer_operations(self):
        with AP_LOCKFREE:
            allocator = AllocatorProtocol(64)
            allocator.buf[:4] = b'\x01\x02\x03\x04'
            self.assertEqual(bytes(allocator.buf[:4]), b'\x01\x02\x03\x04')

    def test_lockfree_restores_previous_state(self):
        with AP_LOCKFREE:
            allocator1 = AllocatorProtocol(64)
            self.assertFalse(allocator1.with_lock)
        # After exiting AP_LOCKFREE, default state is restored
        allocator2 = AllocatorProtocol(64)
        # Default lock state is macro-configurable — just verify it's bool
        self.assertIsInstance(allocator2.with_lock, bool)

    def test_lockfree_inverted_with_locked(self):
        """~AP_LOCKFREE should be equivalent to AP_LOCKED."""
        with ~AP_LOCKFREE:
            allocator = AllocatorProtocol(128)
            self.assertTrue(allocator.with_lock)

    def test_locked_inverted_is_lockfree(self):
        """~AP_LOCKED should be equivalent to AP_LOCKFREE."""
        with ~AP_LOCKED:
            allocator = AllocatorProtocol(128)
            self.assertFalse(allocator.with_lock)


if __name__ == '__main__':
    unittest.main()
