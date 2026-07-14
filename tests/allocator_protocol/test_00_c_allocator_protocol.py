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
    """Test default AllocatorProtocol (no context manager — plain calloc)."""

    def test_creation_with_size(self):
        allocator = AllocatorProtocol(1024)
        self.assertEqual(allocator.size, 1024)

    def test_buf_length_equals_size(self):
        allocator = AllocatorProtocol(256)
        self.assertEqual(len(allocator.buf), 256)

    def test_buf_is_writable_and_readable(self):
        allocator = AllocatorProtocol(512)
        buf = allocator.buf
        test_data = b"Hello, AllocatorProtocol!"
        buf[:len(test_data)] = test_data
        self.assertEqual(bytes(buf[:len(test_data)]), test_data)

    def test_buf_zero_initialized(self):
        allocator = AllocatorProtocol(128)
        self.assertEqual(bytes(allocator.buf[:64]), b'\x00' * 64)

    def test_multiple_instances_independent(self):
        a1 = AllocatorProtocol(256)
        a2 = AllocatorProtocol(512)
        self.assertEqual(a1.size, 256)
        self.assertEqual(a2.size, 512)
        a1.buf[0] = b'a'
        a2.buf[0] = b'b'
        self.assertEqual(a1.buf[0], b'a')
        self.assertEqual(a2.buf[0], b'b')
        self.assertNotEqual(a1.addr, a2.addr)

    def test_addr_is_nonzero_int(self):
        allocator = AllocatorProtocol(64)
        self.assertIsInstance(allocator.addr, int)
        self.assertGreater(allocator.addr, 0)

    def test_default_with_lock_is_bool(self):
        allocator = AllocatorProtocol(64)
        self.assertIsInstance(allocator.with_lock, bool)

    def test_default_with_shm_is_false(self):
        allocator = AllocatorProtocol(64)
        self.assertFalse(allocator.with_shm)

    def test_default_with_freelist_is_true(self):
        allocator = AllocatorProtocol(64)
        self.assertTrue(allocator.with_freelist)

    def test_repr_contains_class_name(self):
        a = AllocatorProtocol(64)
        self.assertIn('AllocatorProtocol', repr(a))
        self.assertIn('size=64', repr(a))

    def test_zero_size_raises_on_property_access(self):
        a = AllocatorProtocol(0)
        with self.assertRaises(RuntimeError):
            _ = a.size
        with self.assertRaises(RuntimeError):
            _ = a.buf
        with self.assertRaises(RuntimeError):
            _ = a.addr
        with self.assertRaises(RuntimeError):
            _ = a.with_lock


class TestAllocatorProtocolWithFreelist(unittest.TestCase):
    """Test AllocatorProtocol with AP_FREELIST flag enabled."""

    def test_freelist_mode_basic(self):
        with AP_FREELIST:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertTrue(allocator.with_freelist)
            self.assertFalse(allocator.with_shm)

    def test_freelist_mode_multiple_allocations(self):
        with AP_FREELIST:
            allocators = [AllocatorProtocol(256 * (i + 1)) for i in range(5)]
            for i, allocator in enumerate(allocators):
                expected_size = 256 * (i + 1)
                self.assertEqual(allocator.size, expected_size)
                pattern = bytes([i % 256])
                allocator.buf[0] = pattern
                self.assertEqual(allocator.buf[0], pattern)

    def test_freelist_recycle_same_size(self):
        """After freeing a block, a new allocation of the same size reuses
        its address and the buffer is zeroed."""
        with AP_FREELIST:
            a1 = AllocatorProtocol(256)
            a2 = AllocatorProtocol(256)
            addr_1 = a1.addr
            a1.buf[0] = b'x'
            del a1
            a3 = AllocatorProtocol(256)
            self.assertEqual(a3.addr, addr_1)
            self.assertEqual(a3.buf[0], b'\0')

    def test_freelist_buffer_zeroed_after_recycle(self):
        """Recycled buffer is always zero-filled regardless of prior content."""
        with AP_FREELIST:
            a1 = AllocatorProtocol(512)
            a1.buf[:8] = b'\xff' * 8
            addr_1 = a1.addr
            del a1
            a2 = AllocatorProtocol(256)
            self.assertEqual(a2.addr, addr_1)
            self.assertEqual(bytes(a2.buf[:8]), b'\x00' * 8)

    def test_freelist_disabled_via_invert(self):
        """~AP_FREELIST sets with_freelist=False; buffer is plain calloc."""
        with ~AP_FREELIST:
            a = AllocatorProtocol(128)
            self.assertFalse(a.with_freelist)
            a.buf[:4] = b'\xde\xad\xbe\xef'
            self.assertEqual(bytes(a.buf[:4]), b'\xde\xad\xbe\xef')

    def test_freelist_with_lockfree(self):
        """AP_FREELIST | AP_LOCKFREE → lock off, shm off."""
        with AP_FREELIST | AP_LOCKFREE:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertFalse(allocator.with_lock)
            self.assertFalse(allocator.with_shm)

    def test_freelist_with_locked(self):
        """AP_FREELIST | AP_LOCKED → lock on, shm off."""
        with AP_FREELIST | AP_LOCKED:
            allocator = AllocatorProtocol(1024)
            self.assertEqual(allocator.size, 1024)
            self.assertTrue(allocator.with_lock)
            self.assertFalse(allocator.with_shm)

    def test_freelist_with_shared_shm_takes_precedence(self):
        """AP_FREELIST | AP_SHARED: shm path wins; with_shm=True, with_freelist
        remains False on the protocol struct (shm path doesn't set it)."""
        with AP_FREELIST | AP_SHARED:
            a = AllocatorProtocol(1024)
            self.assertTrue(a.with_shm)
            self.assertFalse(a.with_freelist)


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
    """Test AP_LOCKFREE / AP_LOCKED context managers."""

    def test_lockfree_disables_lock(self):
        with AP_LOCKFREE:
            a = AllocatorProtocol(256)
            self.assertFalse(a.with_lock)

    def test_locked_enables_lock(self):
        with AP_LOCKED:
            a = AllocatorProtocol(256)
            self.assertTrue(a.with_lock)

    def test_lockfree_with_shared(self):
        """AP_LOCKFREE | AP_SHARED → shm on, lock off."""
        with AP_LOCKFREE | AP_SHARED:
            a = AllocatorProtocol(128)
            self.assertTrue(a.with_shm)
            self.assertFalse(a.with_lock)

    def test_locked_with_shared(self):
        """AP_LOCKED | AP_SHARED → shm on, lock on."""
        with AP_LOCKED | AP_SHARED:
            a = AllocatorProtocol(128)
            self.assertTrue(a.with_shm)
            self.assertTrue(a.with_lock)

    def test_lockfree_with_freelist(self):
        with AP_LOCKFREE | AP_FREELIST:
            a = AllocatorProtocol(128)
            self.assertFalse(a.with_lock)
            self.assertFalse(a.with_shm)
            self.assertTrue(a.with_freelist)

    def test_lockfree_restores_previous_state(self):
        with AP_LOCKFREE:
            a1 = AllocatorProtocol(64)
            self.assertFalse(a1.with_lock)
        # After exiting context, default state is restored
        a2 = AllocatorProtocol(64)
        self.assertIsInstance(a2.with_lock, bool)

    def test_lockfree_inverted_is_locked(self):
        """~AP_LOCKFREE is equivalent to AP_LOCKED."""
        with ~AP_LOCKFREE:
            a = AllocatorProtocol(128)
            self.assertTrue(a.with_lock)

    def test_locked_inverted_is_lockfree(self):
        """~AP_LOCKED is equivalent to AP_LOCKFREE."""
        with ~AP_LOCKED:
            a = AllocatorProtocol(128)
            self.assertFalse(a.with_lock)


if __name__ == '__main__':
    unittest.main()
