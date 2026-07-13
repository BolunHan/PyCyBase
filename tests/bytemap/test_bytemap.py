"""Test suite for ByteMap — the void* variant (str/bytes → PyObject*).

Port of Quark test_07_c_bytemap.py, adapted for PyCyBase.
"""
import gc
import math
import multiprocessing
import os
import unittest

from cbase.bytemap.c_bytemap import BoundByteMap, BoundByteSet, ByteMap, ByteMapPerformanceTestToolkit


class TestByteMapCreate(unittest.TestCase):
    """Test ByteMap creation and destruction."""

    def test_create_default(self):
        """Test creating ByteMap with default capacity."""
        bmap = ByteMap()
        self.assertIsNotNone(bmap)
        self.assertEqual(len(bmap), 0)
        self.assertGreater(bmap.capacity, 0)
        self.assertEqual(bmap.occupied, 0)
        self.assertEqual(bmap.size, 0)

    def test_create_with_capacity(self):
        """Test creating ByteMap with specified capacity."""
        bmap = ByteMap(init_capacity=128)
        self.assertIsNotNone(bmap)
        self.assertGreaterEqual(bmap.capacity, 128)
        self.assertEqual(len(bmap), 0)

    def test_create_min_capacity(self):
        """Test creating ByteMap with capacity below minimum."""
        bmap = ByteMap(init_capacity=1)
        self.assertIsNotNone(bmap)
        # Should clamp up to MIN_BYTEMAP_CAPACITY (16)
        self.assertGreaterEqual(bmap.capacity, 16)

    def test_destroy(self):
        """Test ByteMap is properly destroyed."""
        bmap = ByteMap(init_capacity=64)
        bmap['key1'] = 'value1'
        bmap['key2'] = 'value2'
        del bmap
        gc.collect()
        # If this doesn't crash, destruction worked


class TestByteMapBasicKV(unittest.TestCase):
    """Test basic key-value operations."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_set_get_str_key(self):
        """Test set and get with string keys."""
        value = {'data': 42}
        self.values.append(value)

        self.bmap['test_key'] = value
        self.assertEqual(len(self.bmap), 1)

        result = self.bmap['test_key']
        self.assertIs(result, value)
        self.assertEqual(result['data'], 42)

    def test_set_get_bytes_key(self):
        """Test set and get with bytes keys."""
        value = [1, 2, 3, 4]
        self.values.append(value)

        key = b'bytes_key'
        self.bmap[key] = value
        self.assertEqual(len(self.bmap), 1)

        result = self.bmap[key]
        self.assertIs(result, value)
        self.assertEqual(result, [1, 2, 3, 4])

    def test_set_update_existing(self):
        """Test updating an existing key."""
        value1 = {'version': 1}
        value2 = {'version': 2}
        self.values.extend([value1, value2])

        self.bmap['key'] = value1
        self.assertEqual(len(self.bmap), 1)
        self.assertEqual(self.bmap['key']['version'], 1)

        self.bmap['key'] = value2
        self.assertEqual(len(self.bmap), 1)
        self.assertEqual(self.bmap['key']['version'], 2)

    def test_get_missing_key(self):
        """Test getting a non-existent key raises KeyError."""
        with self.assertRaises(KeyError):
            _ = self.bmap['missing']

    def test_get_method_with_default(self):
        """Test get() method with default value."""
        value = self.bmap.get('missing', 'default')
        self.assertEqual(value, 'default')

        self.bmap['exists'] = 'found'
        self.values.append('found')
        value = self.bmap.get('exists', 'default')
        self.assertEqual(value, 'found')

    def test_contains(self):
        """Test 'in' operator and contains() method."""
        value = 'test_value'
        self.values.append(value)

        self.assertNotIn('key', self.bmap)
        self.assertFalse(self.bmap.contains('key'))

        self.bmap['key'] = value
        self.assertIn('key', self.bmap)
        self.assertTrue(self.bmap.contains('key'))

    def test_multiple_entries(self):
        """Test adding multiple key-value pairs."""
        entries = {
            'key1': {'val': 1},
            'key2': {'val': 2},
            'key3': {'val': 3},
            b'key4': {'val': 4},
            b'key5': {'val': 5},
        }

        for key, value in entries.items():
            self.values.append(value)
            self.bmap[key] = value

        self.assertEqual(len(self.bmap), 5)

        for key, expected_value in entries.items():
            result = self.bmap[key]
            self.assertIs(result, expected_value)


class TestByteMapPop(unittest.TestCase):
    """Test pop operations."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_pop_existing(self):
        """Test popping an existing key."""
        value = {'data': 'test'}
        self.values.append(value)

        self.bmap['key'] = value
        self.assertEqual(len(self.bmap), 1)

        self.bmap.pop('key')
        self.assertEqual(len(self.bmap), 0)
        self.assertNotIn('key', self.bmap)

    def test_pop_missing_no_default(self):
        """Test popping a non-existent key without default raises KeyError."""
        with self.assertRaises(KeyError):
            self.bmap.pop('missing')

    def test_pop_missing_with_default(self):
        """Test popping a non-existent key with default."""
        result = self.bmap.pop('missing', 'default_value')
        self.assertEqual(result, 'default_value')

    def test_pop_order(self):
        """Test that multiple pops maintain integrity."""
        for i in range(5):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.assertEqual(len(self.bmap), 5)

        self.bmap.pop('key2')
        self.assertEqual(len(self.bmap), 4)
        self.assertNotIn('key2', self.bmap)

        # Other keys should still be accessible
        for i in [0, 1, 3, 4]:
            self.assertIn(f'key{i}', self.bmap)


class TestByteMapClear(unittest.TestCase):
    """Test clear operations."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_clear_empty(self):
        """Test clearing an empty map."""
        self.bmap.clear()
        self.assertEqual(len(self.bmap), 0)

    def test_clear_populated(self):
        """Test clearing a populated map."""
        for i in range(10):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.assertEqual(len(self.bmap), 10)

        self.bmap.clear()
        self.assertEqual(len(self.bmap), 0)
        self.assertEqual(self.bmap.occupied, 0)

        # Map should still be usable after clear
        new_value = 'new'
        self.values.append(new_value)
        self.bmap['new_key'] = new_value
        self.assertEqual(len(self.bmap), 1)


class TestByteMapIteration(unittest.TestCase):
    """Test iteration over keys and values."""

    def setUp(self):
        """Create a fresh ByteMap with test data."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

        self.test_data_str = {
            'alpha': {'id': 1},
            'beta': {'id': 2},
            'gamma': {'id': 3},
        }
        self.test_data_bytes = {
            b'delta': {'id': 4},
            b'epsilon': {'id': 5},
        }

        for key, value in self.test_data_str.items():
            self.values.append(value)
            self.bmap[key] = value

        for key, value in self.test_data_bytes.items():
            self.values.append(value)
            self.bmap[key] = value

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_str_keys(self):
        """Test iterating over string keys."""
        keys = list(self.bmap.str_keys())
        self.assertEqual(len(keys), 5)

        for key in self.test_data_str.keys():
            self.assertIn(key, keys)

    def test_bytes_keys(self):
        """Test iterating over bytes keys."""
        keys = list(self.bmap.bytes_keys())
        self.assertEqual(len(keys), 5)

        for key in self.test_data_bytes.keys():
            self.assertIn(key, keys)

        for key in self.test_data_str.keys():
            self.assertIn(key.encode('utf-8'), keys)

    def test_values(self):
        """Test iterating over values (as addresses)."""
        values = list(self.bmap.values())
        self.assertEqual(len(values), 5)

        for val in values:
            self.assertIsInstance(val, int)
            self.assertGreater(val, 0)

    def test_insertion_order(self):
        """Test that iteration maintains insertion order."""
        ordered_keys = ['first', 'second', 'third', 'fourth']
        ordered_values = []

        for key in ordered_keys:
            value = {'key': key}
            ordered_values.append(value)
            self.bmap[key] = value

        result_keys = list(self.bmap.str_keys())

        for expected, actual in zip(ordered_keys, result_keys[-4:]):
            self.assertEqual(expected, actual)


class TestByteMapRehash(unittest.TestCase):
    """Test rehashing and capacity management."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=16)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_manual_rehash(self):
        """Test manually setting capacity."""
        initial_capacity = self.bmap.capacity

        for i in range(5):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.bmap.capacity = initial_capacity * 2
        self.assertGreaterEqual(self.bmap.capacity, initial_capacity * 2)

        self.assertEqual(len(self.bmap), 5)
        for i in range(5):
            self.assertIn(f'key{i}', self.bmap)

    def test_auto_growth(self):
        """Test that map grows automatically when needed."""
        initial_capacity = self.bmap.capacity

        num_entries = initial_capacity
        for i in range(num_entries):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.assertGreater(self.bmap.capacity, initial_capacity)

        self.assertEqual(len(self.bmap), num_entries)
        for i in range(num_entries):
            self.assertIn(f'key{i}', self.bmap)


class TestByteMapPatchedBehavior(unittest.TestCase):
    """Contract:
    - Updating existing keys must not trigger capacity growth.
    - Tombstone reuse on insert must not trigger capacity growth.
    - Fresh-slot inserts at threshold may trigger growth and keep data valid.
    """

    def setUp(self):
        self.bmap = ByteMap(init_capacity=16)
        self.values = []

    def tearDown(self):
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    @staticmethod
    def _find_collision_key(bmap, base_key, capacity):
        target_bucket = bmap.hash(base_key) % capacity
        for i in range(1, 200000):
            candidate = f"{base_key}#col#{i:06d}"
            if candidate == base_key:
                continue
            if bmap.hash(candidate) % capacity == target_bucket:
                return candidate
        raise AssertionError("Failed to find a colliding key for tombstone reuse test")

    def test_00_update_existing_at_threshold_does_not_rehash(self):
        initial_capacity = self.bmap.capacity
        n = initial_capacity // 2

        for i in range(n):
            value = {'v': i}
            self.values.append(value)
            self.bmap[f'key_{i:03d}'] = value

        cap_before_update = self.bmap.capacity
        self.assertEqual(cap_before_update, initial_capacity)
        self.assertEqual(self.bmap.occupied, n)

        for i in range(n):
            value = {'v': i + 10_000}
            self.values.append(value)
            self.bmap[f'key_{i:03d}'] = value

        self.assertEqual(self.bmap.capacity, cap_before_update)
        self.assertEqual(self.bmap.size, n)
        self.assertEqual(self.bmap.occupied, n)
        for i in range(n):
            self.assertEqual(self.bmap[f'key_{i:03d}']['v'], i + 10_000)

    def test_01_tombstone_reuse_at_threshold_does_not_rehash(self):
        for mode in ('same_key', 'hash_collision'):
            with self.subTest(mode=mode):
                bmap = ByteMap(init_capacity=16)
                initial_capacity = bmap.capacity
                n = initial_capacity // 2

                for i in range(n):
                    bmap[f'key_{i:03d}'] = float(i)

                victim_key = 'key_000'
                bmap.pop(victim_key)
                cap_before_insert = bmap.capacity
                occupied_before_insert = bmap.occupied

                if mode == 'same_key':
                    insert_key = victim_key
                else:
                    insert_key = self._find_collision_key(bmap, victim_key, cap_before_insert)

                bmap[insert_key] = 999.0

                self.assertEqual(bmap.capacity, cap_before_insert)
                self.assertEqual(bmap.occupied, occupied_before_insert)
                self.assertEqual(bmap.size, n)
                self.assertEqual(bmap[insert_key], 999.0)

    def test_02_fresh_slot_insert_at_threshold_can_grow(self):
        initial_capacity = self.bmap.capacity
        n = initial_capacity // 2

        for i in range(n):
            value = {'v': i}
            self.values.append(value)
            self.bmap[f'key_{i:03d}'] = value

        self.assertEqual(self.bmap.capacity, initial_capacity)
        extra_value = {'v': -1}
        self.values.append(extra_value)
        self.bmap['key_extra'] = extra_value

        self.assertGreaterEqual(self.bmap.capacity, initial_capacity)
        self.assertIn('key_extra', self.bmap)
        for i in range(n):
            self.assertIn(f'key_{i:03d}', self.bmap)


class TestByteMapAddressInterface(unittest.TestCase):
    """Test low-level address-based interface."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        del self.bmap
        gc.collect()

    def test_set_get_addr(self):
        """Test setting and getting raw addresses."""
        addr = 0x12345678

        self.bmap.set_addr('key', addr)
        result = self.bmap.get_addr('key')

        self.assertEqual(result, addr)

    def test_mixed_object_and_addr(self):
        """Test that object interface and address interface share the same storage."""
        value = {'data': 'test'}
        self.bmap['obj_key'] = value

        addr = self.bmap.get_addr('obj_key')
        self.assertIsInstance(addr, int)
        self.assertGreater(addr, 0)

        result = self.bmap['obj_key']
        self.assertIs(result, value)


class TestByteMapEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_empty_string_key(self):
        """Test using empty string as key."""
        value = 'value'
        self.values.append(value)

        with self.assertRaises(KeyError):
            self.bmap[''] = value

    def test_empty_bytes_key(self):
        """Test using empty bytes as key."""
        value = 'value'
        self.values.append(value)

        with self.assertRaises(KeyError):
            self.bmap[b''] = value

    def test_invalid_key_type(self):
        """Test using invalid key type."""
        value = 'value'
        self.values.append(value)

        with self.assertRaises(TypeError):
            self.bmap[123] = value

        with self.assertRaises(TypeError):
            self.bmap[None] = value

    def test_none_value(self):
        """Test storing None as value."""
        self.bmap['key'] = None
        result = self.bmap['key']
        self.assertIsNone(result)

    def test_unicode_keys(self):
        """Test using Unicode string keys."""
        value = 'test'
        self.values.append(value)

        keys = ['αβγδ', '中文', '🚀🌟', 'Ñoño']
        for key in keys:
            self.bmap[key] = value

        self.assertEqual(len(self.bmap), len(keys))

        for key in keys:
            self.assertIn(key, self.bmap)

    def test_long_keys(self):
        """Test using very long keys."""
        value = 'test'
        self.values.append(value)

        long_key = 'x' * 1000
        self.bmap[long_key] = value

        self.assertIn(long_key, self.bmap)
        self.assertEqual(self.bmap[long_key], value)

    def test_many_entries(self):
        """Test adding many entries to ensure stability."""
        num_entries = 1000

        for i in range(num_entries):
            value = {'index': i}
            self.values.append(value)
            self.bmap[f'key_{i:04d}'] = value

        self.assertEqual(len(self.bmap), num_entries)

        for i in range(num_entries):
            key = f'key_{i:04d}'
            self.assertIn(key, self.bmap)
            self.assertEqual(self.bmap[key]['index'], i)


class TestByteMapProperties(unittest.TestCase):
    """Test ByteMap properties."""

    def setUp(self):
        """Create a fresh ByteMap for each test."""
        self.bmap = ByteMap(init_capacity=32)
        self.values = []

    def tearDown(self):
        """Clean up references."""
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_occupied_property(self):
        """Test occupied property tracks live + tombstone entries."""
        self.assertEqual(self.bmap.occupied, 0)

        for i in range(5):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.assertEqual(self.bmap.occupied, 5)

        self.bmap.pop('key2')
        self.assertEqual(self.bmap.occupied, 5)

    def test_size_property(self):
        """Test size property."""
        for i in range(5):
            value = f'value{i}'
            self.values.append(value)
            self.bmap[f'key{i}'] = value

        self.bmap.pop('key2')

        self.assertEqual(self.bmap.size, 4)
        self.assertGreater(self.bmap.occupied, self.bmap.size)

    def test_salt_property(self):
        """Test salt property can be read and written."""
        original_salt = self.bmap.salt
        self.assertIsInstance(original_salt, int)
        self.assertGreater(original_salt, 0)

        new_salt = 0x123456789ABCDEF0
        self.bmap.salt = new_salt
        self.assertEqual(self.bmap.salt, new_salt)

    def test_repr(self):
        """Test string representation."""
        repr_str = repr(self.bmap)
        self.assertIn('ByteMap', repr_str)
        self.assertIn('capacity', repr_str)
        self.assertIn('occupied', repr_str)

    def test_copy(self):
        """Test copy creates an independent clone."""
        value = {'data': 'test'}
        self.values.append(value)
        self.bmap['key'] = value

        import copy
        bmap2 = copy.copy(self.bmap)
        self.assertIsNot(bmap2, self.bmap)
        self.assertEqual(bmap2['key'], value)

        # Modify original, copy should be unaffected
        value2 = {'data': 'other'}
        self.values.append(value2)
        self.bmap['key'] = value2
        self.assertEqual(bmap2['key'], value)

        del bmap2

    def test_slot_capacity(self):
        """Test that ByteMap has sizeof(void*) slot capacity."""
        # slot_capacity is a cdef field - verify indirectly
        # by checking we can store and retrieve a pointer value
        import sys
        value = object()
        self.values.append(value)
        self.bmap['test'] = value
        result = self.bmap['test']
        self.assertIs(result, value)


class TestBoundByteMapAPI(unittest.TestCase):
    """Test BoundByteMap API behavior and result correctness."""

    def setUp(self):
        self.bmap = BoundByteMap()
        self.values = []

    def tearDown(self):
        self.bmap.clear()
        self.values.clear()
        del self.bmap
        gc.collect()

    def test_create_and_basic_set_get(self):
        """BoundByteMap should accept set/get and preserve object identity."""
        value = {'x': 1}
        self.values.append(value)

        self.bmap['alpha'] = value
        self.assertEqual(len(self.bmap), 1)
        self.assertIn('alpha', self.bmap)
        self.assertIs(self.bmap['alpha'], value)

    def test_update_and_len(self):
        """update() should insert all payload items correctly."""
        payload = {
            'k1': {'v': 1},
            'k2': {'v': 2},
            'k3': {'v': 3},
        }
        self.values.extend(payload.values())

        self.bmap.update(payload)
        self.assertEqual(len(self.bmap), 3)
        for key, expected in payload.items():
            self.assertIn(key, self.bmap)
            self.assertIs(self.bmap[key], expected)

    def test_setdefault_semantics(self):
        """setdefault() should match dict semantics for hit and miss."""
        d1 = {'ok': True}
        d2 = {'ok': False}
        self.values.extend([d1, d2])

        out = self.bmap.setdefault('slot', d1)
        self.assertIs(out, d1)
        self.assertEqual(len(self.bmap), 1)

        out = self.bmap.setdefault('slot', d2)
        self.assertIs(out, d1)
        self.assertIs(self.bmap['slot'], d1)
        self.assertEqual(len(self.bmap), 1)

    def test_pop_semantics(self):
        """pop() should return stored value and honor default for missing key."""
        value = {'pop': 1}
        self.values.append(value)
        self.bmap['target'] = value

        out = self.bmap.pop('target')
        self.assertIs(out, value)
        self.assertNotIn('target', self.bmap)
        self.assertEqual(len(self.bmap), 0)

        sentinel = object()
        out = self.bmap.pop('missing', sentinel)
        self.assertIs(out, sentinel)

        with self.assertRaises(KeyError):
            self.bmap.pop('missing_without_default')

    def test_clear_syncs_python_view(self):
        """clear() should clear the mapping contents correctly."""
        for i in range(5):
            value = {'id': i}
            self.values.append(value)
            self.bmap[f'k{i}'] = value

        self.assertEqual(len(self.bmap), 5)
        self.bmap.clear()
        self.assertEqual(len(self.bmap), 0)
        self.assertNotIn('k0', self.bmap)

    def test_bytes_key_roundtrip(self):
        """Bytes keys should be accepted and retrievable as bytes keys."""
        value = ['bytes']
        self.values.append(value)
        key = b'blob-key'

        self.bmap[key] = value
        self.assertIn(key, self.bmap)
        self.assertIs(self.bmap[key], value)

    def test_init_from_kwargs_and_mapping(self):
        """Constructor payload should populate entries correctly."""
        v1 = {'n': 1}
        v2 = {'n': 2}
        self.values.extend([v1, v2])

        bmap = BoundByteMap({'a': v1}, b=v2)
        try:
            self.assertEqual(len(bmap), 2)
            self.assertIs(bmap['a'], v1)
            self.assertIs(bmap['b'], v2)
        finally:
            bmap.clear()
            del bmap

    def test_fork(self):
        bmap0 = BoundByteMap()
        bmap1 = bmap0.fork()
        v = ['a', 'b', 'c']
        bmap0['abc'] = v
        self.assertIs(bmap1['abc'], v)
        del bmap1
        gc.collect()
        self.assertIn('abc', bmap0)
        bmap2 = bmap0.fork()
        bmap2.clear()
        self.assertNotIn('abc', bmap0)

    def test_rebind_from_bound_map_refreshes_cache(self):
        src = BoundByteMap()
        dst = BoundByteMap()
        try:
            src['fresh'] = {'v': 1}
            dst['stale'] = {'v': 2}

            dst.rebind(src)
            self.assertIn('fresh', dst)
            self.assertNotIn('stale', dst)
        finally:
            src.clear()
            dst.clear()

    def test_rebind_from_bytemap_refreshes_cache(self):
        src = BoundByteMap()
        dst = BoundByteMap()
        try:
            src['k1'] = {'ok': 1}
            dst['stale'] = {'ok': 0}

            dst.rebind(src)
            self.assertIn('k1', dst)
            self.assertNotIn('stale', dst)
        finally:
            src.clear()
            dst.clear()

    def test_rebind_from_bound_set_is_rejected(self):
        src = BoundByteSet(['a'])
        with self.assertRaises(TypeError):
            self.bmap.rebind(src)
        src.clear()

    def test_freed(self):
        bd = BoundByteMap()
        bd_forked = bd.fork()
        bd['abc'] = 123

        self.assertEqual(bd_forked['abc'], 123)

        del bd
        gc.collect()

        self.assertFalse(bool(bd_forked))


class TestBoundByteSetAPI(unittest.TestCase):
    """Test BoundByteSet API behavior and result correctness."""

    def setUp(self):
        self.bset = BoundByteSet()

    def tearDown(self):
        self.bset.clear()
        del self.bset
        gc.collect()

    def test_create_and_basic_add_contains(self):
        """BoundByteSet should accept add and support membership testing."""
        self.bset.add('alpha')
        self.assertEqual(len(self.bset), 1)
        self.assertIn('alpha', self.bset)
        self.assertNotIn('beta', self.bset)

    def test_update_and_len(self):
        """update() should insert all iterable members correctly."""
        members = {'k1', 'k2', 'k3'}
        self.bset.update(members)
        self.assertEqual(len(self.bset), 3)
        for member in members:
            self.assertIn(member, self.bset)

    def test_add_multiple(self):
        """Multiple add() calls should increase set size correctly."""
        for i in range(5):
            self.bset.add(f'elem{i}')

        self.assertEqual(len(self.bset), 5)
        for i in range(5):
            self.assertIn(f'elem{i}', self.bset)

    def test_discard_semantics(self):
        """discard() should remove element without raising if missing."""
        self.bset.add('target')
        self.assertIn('target', self.bset)

        self.bset.discard('target')
        self.assertNotIn('target', self.bset)
        self.assertEqual(len(self.bset), 0)

        self.bset.discard('missing')
        self.assertEqual(len(self.bset), 0)

    def test_remove_semantics(self):
        """remove() should raise KeyError if element is missing."""
        self.bset.add('target')
        self.assertIn('target', self.bset)

        self.bset.remove('target')
        self.assertNotIn('target', self.bset)
        self.assertEqual(len(self.bset), 0)

        with self.assertRaises(KeyError):
            self.bset.remove('missing')

    def test_pop_semantics(self):
        """pop() should return and remove an arbitrary element."""
        self.bset.update(['elem1', 'elem2', 'elem3'])
        self.assertEqual(len(self.bset), 3)

        elem = self.bset.pop()
        self.assertIsInstance(elem, str)
        self.assertNotIn(elem, self.bset)
        self.assertEqual(len(self.bset), 2)

        self.bset.clear()
        with self.assertRaises(KeyError):
            self.bset.pop()

    def test_clear_syncs_python_view(self):
        """clear() should clear all elements correctly."""
        for i in range(5):
            self.bset.add(f'k{i}')

        self.assertEqual(len(self.bset), 5)
        self.bset.clear()
        self.assertEqual(len(self.bset), 0)
        self.assertNotIn('k0', self.bset)

    def test_bytes_member_roundtrip(self):
        """Bytes members should be accepted and retrievable."""
        member = b'blob-member'
        self.bset.add(member)
        self.assertIn(member, self.bset)
        self.assertEqual(len(self.bset), 1)

    def test_init_from_iterable(self):
        """Constructor should populate set from iterable correctly."""
        members = ['a', 'b', 'c']
        bset = BoundByteSet(members)
        try:
            self.assertEqual(len(bset), 3)
            for member in members:
                self.assertIn(member, bset)
        finally:
            bset.clear()
            del bset

    def test_mixed_str_bytes(self):
        """Set should handle both str and bytes members."""
        self.bset.add('string_member')
        self.bset.add(b'bytes_member')

        self.assertEqual(len(self.bset), 2)
        self.assertIn('string_member', self.bset)
        self.assertIn(b'bytes_member', self.bset)
        self.assertNotIn('bytes_member', self.bset)
        self.assertNotIn(b'string_member', self.bset)

    def test_duplicate_add(self):
        """Adding duplicate element should not increase set size."""
        self.bset.add('duplicate')
        self.assertEqual(len(self.bset), 1)

        self.bset.add('duplicate')
        self.assertEqual(len(self.bset), 1)
        self.assertIn('duplicate', self.bset)

    def test_update_with_duplicates(self):
        """update() should handle duplicates correctly."""
        self.bset.add('existing')
        self.bset.update(['existing', 'new1', 'new2', 'new1'])

        self.assertEqual(len(self.bset), 3)
        self.assertIn('existing', self.bset)
        self.assertIn('new1', self.bset)
        self.assertIn('new2', self.bset)

    def test_fork(self):
        """fork() should create a non-owning view sharing the same bytemap."""
        bset0 = BoundByteSet()
        bset1 = bset0.fork()

        bset0.add('abc')
        self.assertIn('abc', bset1)

        del bset1
        gc.collect()
        self.assertIn('abc', bset0)

        bset2 = bset0.fork()
        bset2.clear()
        self.assertNotIn('abc', bset0)

        bset0.clear()
        del bset2

    def test_rebind_from_bound_set_refreshes_cache(self):
        src = BoundByteSet(['a', 'b'])
        dst = BoundByteSet(['stale'])
        try:
            dst.rebind(src)
            self.assertIn('a', dst)
            self.assertIn('b', dst)
            self.assertNotIn('stale', dst)
        finally:
            src.clear()
            dst.clear()

    def test_rebind_from_bound_map_refreshes_cache(self):
        src = BoundByteMap({'m1': object(), 'm2': object()})
        dst = BoundByteSet(['stale'])
        try:
            dst.rebind(src)
            self.assertIn('m1', dst)
            self.assertIn('m2', dst)
            self.assertNotIn('stale', dst)
        finally:
            src.clear()
            dst.clear()

    def test_unicode_members(self):
        """Set should handle Unicode string members."""
        members = ['αβγδ', '中文', '🚀🌟', 'Ñoño']
        self.bset.update(members)

        self.assertEqual(len(self.bset), len(members))
        for member in members:
            self.assertIn(member, self.bset)

    def test_long_members(self):
        """Set should handle very long string members."""
        long_member = 'x' * 1000
        self.bset.add(long_member)

        self.assertIn(long_member, self.bset)
        self.assertEqual(len(self.bset), 1)

    def test_many_members(self):
        """Set should handle many members correctly."""
        num_members = 500

        for i in range(num_members):
            self.bset.add(f'member_{i:04d}')

        self.assertEqual(len(self.bset), num_members)

        for i in range(num_members):
            key = f'member_{i:04d}'
            self.assertIn(key, self.bset)

    def test_iteration(self):
        """Iteration over set should include all members."""
        members = ['m1', 'm2', 'm3', 'm4', 'm5']
        self.bset.update(members)

        iterated = set(self.bset)
        self.assertEqual(iterated, set(members))

    def test_repr(self):
        """Set should have a meaningful repr."""
        self.bset.add('test')
        repr_str = repr(self.bset)
        self.assertIn('BoundByteSet', repr_str)
        self.assertIn('test', repr_str)

    def test_set_operations_membership(self):
        """Set membership operations should work correctly."""
        self.bset.update(['a', 'b', 'c'])

        self.assertTrue('a' in self.bset)
        self.assertFalse('d' in self.bset)

        self.assertFalse('a' not in self.bset)
        self.assertTrue('d' not in self.bset)

    def test_sequential_operations(self):
        """Sequence of add/remove/check operations should maintain consistency."""
        self.bset.add('e1')
        self.bset.add('e2')
        self.bset.add('e3')
        self.assertEqual(len(self.bset), 3)

        self.bset.remove('e2')
        self.assertEqual(len(self.bset), 2)
        self.assertNotIn('e2', self.bset)
        self.assertIn('e1', self.bset)
        self.assertIn('e3', self.bset)

        self.bset.discard('e1')
        self.assertEqual(len(self.bset), 1)
        self.assertIn('e3', self.bset)

        self.bset.add('e2')
        self.assertEqual(len(self.bset), 2)
        self.assertIn('e2', self.bset)
        self.assertIn('e3', self.bset)

    def test_freed(self):
        bs = BoundByteSet()
        bs_forked = bs.fork()
        bs.add('abc')
        self.assertIn('abc', bs_forked)
        del bs
        gc.collect()
        self.assertFalse(bool(bs_forked))


class TestByteMapPerformanceToolkit(unittest.TestCase):
    """Test the performance toolkit (sanity checks, not benchmarks)."""

    def test_toolkit_run(self):
        toolkit = ByteMapPerformanceTestToolkit(n_iters=10, n_payloads=100)
        stats = toolkit.run_test()

        self.assertGreater(stats['c_set'], 0.0)
        self.assertGreater(stats['py_set'], 0.0)
        self.assertGreater(stats['c_get'], 0.0)
        self.assertGreater(stats['py_get'], 0.0)
        self.assertEqual(stats['c_checksum'], stats['py_checksum'])


class TestSeqIdMultiprocessSafety(unittest.TestCase):
    """Validate that seq_id incorporates PID, so forked processes get distinct seq_ids
    even when operating at identical virtual addresses.

    This is critical for shared-memory (AP_SHARED) scenarios where forked
    worker processes share a bytemap: if two processes had the same seq_id,
    a mutation by process A would be silently suppressed by the bound view
    in process B (because the callback would match B.seq_id).
    """

    def test_00_same_process_same_addr_same_seq_id(self):
        """Within one process, the same address always produces the same seq_id."""
        obj = object()
        addr = id(obj)
        sid1 = ByteMapPerformanceTestToolkit.gen_seq_id(addr)
        sid2 = ByteMapPerformanceTestToolkit.gen_seq_id(addr)
        self.assertEqual(sid1, sid2)

    def test_01_same_process_different_addr_different_seq_id(self):
        """Within one process, two distinct objects should (almost always)
        produce different seq_ids."""
        obj1 = object()
        obj2 = object()
        addr1 = id(obj1)
        addr2 = id(obj2)
        self.assertNotEqual(addr1, addr2)  # different live objects, different addresses
        sid1 = ByteMapPerformanceTestToolkit.gen_seq_id(addr1)
        sid2 = ByteMapPerformanceTestToolkit.gen_seq_id(addr2)
        self.assertNotEqual(sid1, sid2)

    def test_02_different_process_same_addr_different_seq_id(self):
        """After fork, the same virtual address produces a DIFFERENT seq_id
        because the child has a different PID."""
        sentinel = object()
        addr = id(sentinel)
        parent_sid = ByteMapPerformanceTestToolkit.gen_seq_id(addr)

        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()

        def child_worker():
            child_sid = ByteMapPerformanceTestToolkit.gen_seq_id(addr)
            queue.put(child_sid)

        proc = ctx.Process(target=child_worker)
        proc.start()
        proc.join()
        self.assertEqual(proc.exitcode, 0)
        child_sid = queue.get()

        self.assertNotEqual(parent_sid, child_sid,
            f"seq_id collision across processes! parent={parent_sid:#018x} child={child_sid:#018x}")

    def test_03_bound_set_self_suppression_after_fork(self):
        """After fork, a BoundByteSet in the child process correctly
        suppresses its own callbacks (no double-adds)."""
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()

        def child_worker():
            bset = BoundByteSet()
            bset.add('alpha')
            bset.add('beta')
            bset.add('alpha')  # duplicate — should be suppressed
            queue.put(len(bset))  # expected: 2

        proc = ctx.Process(target=child_worker)
        proc.start()
        proc.join()
        self.assertEqual(proc.exitcode, 0)
        self.assertEqual(queue.get(), 2)

    def test_04_bound_map_self_suppression_after_fork(self):
        """After fork, a BoundByteMap in the child process correctly
        suppresses its own callbacks (no double-sets)."""
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()

        def child_worker():
            bmap = BoundByteMap()
            bmap['k1'] = 1
            bmap['k2'] = 2
            bmap['k1'] = 10  # overwrite — should be suppressed
            bmap.pop('k2')
            queue.put((len(bmap), bmap['k1'], 'k2' in bmap))

        proc = ctx.Process(target=child_worker)
        proc.start()
        proc.join()
        self.assertEqual(proc.exitcode, 0)
        size, k1_val, k2_present = queue.get()
        self.assertEqual(size, 1)
        self.assertEqual(k1_val, 10)
        self.assertFalse(k2_present)


if __name__ == '__main__':
    unittest.main()
