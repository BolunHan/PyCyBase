import multiprocessing as mp
import unittest

from cbase.allocator_protocol.c_allocator_protocol import AllocatorProtocol, AP_SHARED, AP_FREELIST, AP_LOCKED


class TestAllocatorProtocolBasic(unittest.TestCase):
    """Test basic AllocatorProtocol functionality with default settings."""

    def test_allocator_creation_with_size(self):
        """Test that AllocatorProtocol can be created with a specific size."""
        size = 1024
        allocator = AllocatorProtocol(size)
        self.assertEqual(allocator.size, size)

    def test_allocator_buffer_access(self):
        """Test that the buffer can be accessed and modified."""
        size = 256
        allocator = AllocatorProtocol(size)
        buf = allocator.buf

        # Should be able to write to the buffer
        buf[0] = b'a'
        self.assertEqual(buf[0], b'a')

    def test_allocator_buffer_write_read(self):
        """Test writing and reading data from the allocator buffer."""
        size = 512
        allocator = AllocatorProtocol(size)
        buf = allocator.buf

        # Write test pattern
        test_data = b"Hello, AllocatorProtocol!"
        buf[:len(test_data)] = test_data

        # Read back and verify
        read_data = bytes(buf[:len(test_data)])
        self.assertEqual(read_data, test_data)

    def test_allocator_multiple_instances(self):
        """Test that multiple AllocatorProtocol instances don't interfere."""
        size1, size2 = 256, 512
        alloc1 = AllocatorProtocol(size1)
        alloc2 = AllocatorProtocol(size2)

        self.assertEqual(alloc1.size, size1)
        self.assertEqual(alloc2.size, size2)

        # Write different patterns
        alloc1.buf[0] = b'a'
        alloc2.buf[0] = b'b'

        self.assertEqual(alloc1.buf[0], b'a')
        self.assertEqual(alloc2.buf[0], b'b')

    def test_allocator_zero_size(self):
        """Test that zero-size allocation is handled gracefully."""
        allocator = AllocatorProtocol(0)
        with self.assertRaises(RuntimeError):
            _ = allocator.size


class TestAllocatorProtocolWithFreelist(unittest.TestCase):
    """Test AllocatorProtocol with AP_FREELIST flag enabled."""

    def test_freelist_mode_basic(self):
        """Test basic allocation with freelist mode."""
        with AP_FREELIST:
            size = 1024
            allocator = AllocatorProtocol(size)
            self.assertEqual(allocator.size, size)
            self.assertFalse(allocator.with_shm)

    def test_freelist_mode_buffer_operations(self):
        """Test buffer read/write operations in freelist mode."""
        with AP_FREELIST:
            allocator = AllocatorProtocol(512)
            buf = allocator.buf

            test_data = b"Freelist mode test"
            buf[:len(test_data)] = test_data

            read_data = bytes(buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_freelist_mode_multiple_allocations(self):
        """Test multiple allocations in freelist mode."""
        with AP_FREELIST:
            allocators = [AllocatorProtocol(256 * (i + 1)) for i in range(5)]

            for i, allocator in enumerate(allocators):
                expected_size = 256 * (i + 1)
                self.assertEqual(allocator.size, expected_size)

                # Write pattern to each
                pattern = bytes([i % 256])
                allocator.buf[0] = pattern
                self.assertEqual(allocator.buf[0], pattern)

    def test_freelist_with_locked_combined(self):
        """Test AP_FREELIST combined with AP_LOCKED."""
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

            # Write to allocator1
            allocator1.buf[0] = b'x'

            # Recycle allocator1
            del allocator1

            # Create new allocator, should reuse the freed one
            allocator3 = AllocatorProtocol(256)
            self.assertEqual(allocator3.addr, addr_1)
            self.assertEqual(allocator3.buf[0], b'\0')  # always zeroed out


class TestAllocatorProtocolWithShared(unittest.TestCase):
    """Test AllocatorProtocol with AP_SHARED (shared memory) flag."""

    def test_shared_mode_basic(self):
        """Test basic allocation with shared memory mode."""
        with AP_SHARED:
            size = 1024
            allocator = AllocatorProtocol(size)
            self.assertEqual(allocator.size, size)
            self.assertTrue(allocator.with_shm)

    def test_shared_mode_buffer_write_read(self):
        """Test buffer operations in shared memory mode."""
        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            buf = allocator.buf

            test_data = b"Shared memory test"
            buf[:len(test_data)] = test_data

            read_data = bytes(buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_shared_mode_child_process_read(self):
        """Test reading from shared memory in child process."""

        def child_process(allocator_id: int) -> bytes:
            """Child process that reads from shared memory."""
            with AP_SHARED:
                allocator = AllocatorProtocol(512)
                # Read the data that parent process wrote
                return bytes(allocator.buf[:len(b"Data from parent")])

        with AP_SHARED:
            allocator = AllocatorProtocol(512)
            test_data = b"Data from parent"
            allocator.buf[:len(test_data)] = test_data

            # Create and run child process
            process = mp.Process(target=child_process, args=(id(allocator),))
            process.start()
            process.join()

            # Parent can still read its data
            read_data = bytes(allocator.buf[:len(test_data)])
            self.assertEqual(read_data, test_data)

    def test_shared_mode_child_process_write_parent_read(self):
        """Test child process writing and parent reading from shared memory."""

        def child_process_write(allocator):
            """Child process that writes to shared memory."""
            self.assertEqual(bytes(allocator.buf[:3]), b'abc')
            allocator.buf[:3] = b'def'

        with AP_SHARED:
            # Initialize allocator with specific values
            allocator = AllocatorProtocol(512)
            allocator.buf[:3] = b'abc'

            # Run child process to write different values
            process = mp.Process(target=child_process_write, args=(allocator,))
            process.start()
            process.join()

            # Parent can read what child wrote
            self.assertEqual(bytes(allocator.buf[:3]), b'def')

    def test_shared_mode_with_locked(self):
        """Test AP_SHARED combined with AP_LOCKED."""
        with AP_SHARED | AP_LOCKED:
            allocator = AllocatorProtocol(1024)
            self.assertTrue(allocator.with_shm)
            self.assertTrue(allocator.with_lock)

    def test_freelist_recycle(self):
        with AP_SHARED | AP_FREELIST:
            allocator1 = AllocatorProtocol(256)
            allocator2 = AllocatorProtocol(256)

            addr_1 = allocator1.addr

            # Write to allocator1
            allocator1.buf[0] = b'x'

            # Recycle allocator1
            del allocator1

            # Create new allocator, should reuse the freed one
            allocator3 = AllocatorProtocol(256)
            self.assertEqual(allocator3.addr, addr_1)
            self.assertEqual(allocator3.buf[0], b'\0')  # always zeroed out


class TestAllocatorProtocolContextManager(unittest.TestCase):
    """Test the context manager functionality of AllocatorProtocol configuration."""

    def test_freelist_context_isolation(self):
        """Test that AP_FREELIST context changes are isolated."""
        # Create without context manager
        alloc1 = AllocatorProtocol(512)
        self.assertFalse(alloc1.with_shm)

        # Create within AP_SHARED context
        with AP_SHARED:
            alloc2 = AllocatorProtocol(512)
            self.assertTrue(alloc2.with_shm)

        # Create after context exits
        alloc3 = AllocatorProtocol(512)
        self.assertFalse(alloc3.with_shm)

    def test_locked_context_isolation(self):
        """Test that AP_LOCKED context changes are isolated."""
        # Create without lock
        alloc1 = AllocatorProtocol(512)
        self.assertFalse(alloc1.with_lock)

        # Create with lock
        with AP_LOCKED:
            alloc2 = AllocatorProtocol(512)
            self.assertTrue(alloc2.with_lock)

        # Create after context exits
        alloc3 = AllocatorProtocol(512)
        self.assertFalse(alloc3.with_lock)

    def test_combined_context_isolation(self):
        """Test combined context managers work correctly."""
        # Default state
        alloc1 = AllocatorProtocol(512)
        self.assertFalse(alloc1.with_shm)
        self.assertFalse(alloc1.with_lock)

        # Within combined context
        with AP_SHARED | AP_LOCKED:
            alloc2 = AllocatorProtocol(512)
            self.assertTrue(alloc2.with_shm)
            self.assertTrue(alloc2.with_lock)

        # After context
        alloc3 = AllocatorProtocol(512)
        self.assertFalse(alloc3.with_shm)
        self.assertFalse(alloc3.with_lock)


class TestAllocatorProtocolProperties(unittest.TestCase):
    """Test AllocatorProtocol property access."""

    def test_properties_accessible(self):
        """Test that all properties are accessible."""
        allocator = AllocatorProtocol(512)

        # Should not raise
        size = allocator.size
        buf = allocator.buf
        with_shm = allocator.with_shm
        with_lock = allocator.with_lock

        self.assertEqual(size, 512)
        self.assertIsNotNone(buf)
        self.assertFalse(with_shm)
        self.assertFalse(with_lock)

    def test_buffer_is_memoryview(self):
        """Test that buf property returns a memoryview-like object."""
        allocator = AllocatorProtocol(512)
        buf = allocator.buf

        # Should support indexing and slicing
        buf[0] = b'a'
        self.assertEqual(buf[0], b'a')

        # Should support slice operations
        test_slice = buf[0:10]
        self.assertEqual(len(test_slice), 10)

    def test_large_buffer_allocation(self):
        """Test allocation of large buffers."""
        size = 1024 * 1024  # 1 MB
        allocator = AllocatorProtocol(size)
        self.assertEqual(allocator.size, size)

        # Write to beginning and end
        allocator.buf[0] = b'1'
        allocator.buf[size - 1] = b'2'

        self.assertEqual(allocator.buf[0], b'1')
        self.assertEqual(allocator.buf[size - 1], b'2')


if __name__ == '__main__':
    unittest.main()
