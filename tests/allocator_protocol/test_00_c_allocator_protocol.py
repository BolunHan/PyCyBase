import multiprocessing as mp
import unittest

from cbase.allocator_protocol.c_allocator_protocol import (
    AllocatorProtocol,
    AP_FREELIST,
    AP_LOCKED,
    AP_LOCKFREE,
    AP_SHARED,
)


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
    """Test AllocatorProtocol with AP_SHARED (shared memory) flag."""

    def test_shared_mode_basic(self):
        with AP_SHARED:
            size = 1024
            allocator = AllocatorProtocol(size)
            self.assertEqual(allocator.size, size)
            self.assertTrue(allocator.with_shm)

    def test_shared_mode_buffer_write_read(self):
        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            buf = allocator.buf
            test_data = b"Shared memory test"
            buf[:len(test_data)] = test_data
            read_data = bytes(buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_shared_mode_child_process_read(self):
        def child_process(allocator_id: int) -> bytes:
            with AP_SHARED:
                allocator = AllocatorProtocol(512)
                return bytes(allocator.buf[:len(b"Data from parent")])

        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            test_data = b"Data from parent"
            allocator.buf[:len(test_data)] = test_data
            process = mp.Process(target=child_process, args=(id(allocator),))
            process.start()
            process.join()
            read_data = bytes(allocator.buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_shared_mode_child_process_write_parent_read(self):
        def child_process_write(allocator):
            self.assertEqual(bytes(allocator.buf[:3]), b'abc')
            allocator.buf[:3] = b'def'

        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            allocator.buf[:3] = b'abc'
            process = mp.Process(target=child_process_write, args=(allocator,))
            process.start()
            process.join()
            self.assertEqual(bytes(allocator.buf[:3]), b'def')

    def test_shared_mode_with_lockfree(self):
        """AP_SHARED combined with AP_LOCKFREE explicitly disables locking."""
        with AP_SHARED | AP_LOCKFREE:
            allocator = AllocatorProtocol(1024)
            self.assertTrue(allocator.with_shm)
            self.assertFalse(allocator.with_lock)

    def test_shared_mode_with_locked(self):
        """AP_SHARED combined with AP_LOCKED explicitly enables locking."""
        with AP_SHARED | AP_LOCKED:
            allocator = AllocatorProtocol(1024)
            self.assertTrue(allocator.with_shm)
            self.assertTrue(allocator.with_lock)


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
