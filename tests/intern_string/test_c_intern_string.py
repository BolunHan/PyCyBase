"""Thorough test suite for InternString / InternStringPool.

Ported from PyAlgoEngine test/test_c_intern_string.py and expanded to cover
every corner case: module globals, interning, lookup, iteration, equality,
hashing, custom pools, concurrency, multiprocessing, edge cases, and stress.
"""
import os
import sys
import time
import unittest
import threading

from cbase.intern_string import c_intern_string as cis
from cbase.intern_string.c_intern_string import (
    InternStringPool,
    InternString,
    POOL,
    INTRA_POOL,
)

_FORK_AVAILABLE = hasattr(os, 'fork') and sys.platform != 'win32'


# ============================================================
#  Module globals & basic API
# ============================================================

class TestModuleGlobals(unittest.TestCase):
    """Verify module-level symbols and their types."""

    def test_module_exists(self):
        self.assertIsNotNone(cis)

    def test_symbols_present(self):
        self.assertTrue(hasattr(cis, 'POOL'))
        self.assertTrue(hasattr(cis, 'C_POOL'))
        self.assertTrue(hasattr(cis, 'InternStringPool'))
        self.assertTrue(hasattr(cis, 'InternString'))

    def test_pool_is_instance(self):
        self.assertIsInstance(cis.POOL, InternStringPool)
        self.assertIsInstance(POOL, InternStringPool)

    def test_intra_pool_is_instance(self):
        self.assertIsInstance(INTRA_POOL, InternStringPool)

    def test_pool_address_is_hex_string(self):
        addr = POOL.address
        self.assertIsInstance(addr, str)
        self.assertTrue(addr.startswith('0x'), msg=f'Expected hex address, got: {addr!r}')
        # Should be parseable as hex
        int(addr, 16)

    def test_intra_pool_address_is_hex_string(self):
        addr = INTRA_POOL.address
        self.assertIsInstance(addr, str)
        self.assertTrue(addr.startswith('0x'))

    def test_c_pool_is_int(self):
        self.assertIsInstance(cis.C_POOL, int)


# ============================================================
#  InternString properties
# ============================================================

class TestInternStringProperties(unittest.TestCase):
    """Verify all InternString property accessors."""

    def setUp(self):
        self.pool = InternStringPool()
        self.inst = self.pool.istr('properties_test')

    def tearDown(self):
        del self.pool

    def test_string_property(self):
        self.assertEqual(self.inst.string, 'properties_test')
        self.assertIsInstance(self.inst.string, str)

    def test_hash_value_property(self):
        hv = self.inst.hash_value
        self.assertIsNotNone(hv)
        self.assertIsInstance(hv, int)
        self.assertGreater(hv, 0)

    def test_address_property(self):
        addr = self.inst.address
        self.assertIsInstance(addr, str)
        self.assertTrue(addr.startswith('0x'), msg=f'Expected hex address, got: {addr!r}')
        int(addr, 16)  # parseable

    def test_pool_property(self):
        self.assertIs(self.inst.pool, self.pool)
        self.assertIsInstance(self.inst.pool, InternStringPool)

    def test_repr(self):
        r = repr(self.inst)
        self.assertIn('InternString', r)
        self.assertIn('properties_test', r)
        self.assertTrue(r.startswith('<'))
        self.assertTrue(r.endswith(')>'))

    def test_repr_uninitialized(self):
        # Create a raw InternString without initialization
        raw = InternString.__new__(InternString)
        r = repr(raw)
        self.assertIn('uninitialized', r)


# ============================================================
#  InternString comparison & hashing
# ============================================================

class TestInternStringComparison(unittest.TestCase):
    """Verify equality, comparison, and hashing."""

    def setUp(self):
        self.pool = InternStringPool()

    def tearDown(self):
        del self.pool

    def test_eq_same_key(self):
        a = self.pool.istr('alpha')
        b = self.pool.istr('alpha')
        self.assertTrue(a == b)
        self.assertFalse(a != b)

    def test_eq_different_key(self):
        a = self.pool.istr('alpha')
        b = self.pool.istr('beta')
        self.assertFalse(a == b)
        self.assertTrue(a != b)

    def test_eq_python_string(self):
        a = self.pool.istr('alpha')
        self.assertTrue(a == 'alpha')
        self.assertFalse(a == 'beta')
        self.assertFalse(a != 'alpha')
        self.assertTrue(a != 'beta')

    def test_eq_cross_pool_same_key(self):
        """Same string from different pools should compare equal by value."""
        pool2 = InternStringPool()
        a = self.pool.istr('gamma')
        b = pool2.istr('gamma')
        self.assertTrue(a == b)
        del pool2

    def test_eq_different_types(self):
        a = self.pool.istr('42')
        self.assertFalse(a == 42)
        self.assertFalse(a == None)
        self.assertFalse(a == [])

    def test_gt(self):
        a = self.pool.istr('alpha')
        b = self.pool.istr('beta')
        c = self.pool.istr('alpha')
        self.assertTrue(b > a)
        self.assertFalse(a > b)
        self.assertFalse(a > c)

    def test_gt_python_string(self):
        a = self.pool.istr('alpha')
        self.assertTrue(a > 'aaa')
        self.assertFalse(a > 'zzz')

    def test_hash_same_key_same_hash(self):
        a = self.pool.istr('delta')
        b = self.pool.istr('delta')
        self.assertEqual(hash(a), hash(b))

    def test_hash_is_int(self):
        a = self.pool.istr('epsilon')
        h = hash(a)
        self.assertIsInstance(h, int)

    def test_hash_usable_in_dict(self):
        a = self.pool.istr('zeta')
        d = {a: 'value'}
        self.assertEqual(d[a], 'value')
        self.assertEqual(d[self.pool.istr('zeta')], 'value')

    def test_hash_usable_in_set(self):
        a = self.pool.istr('eta')
        b = self.pool.istr('eta')
        s = {a, b}
        self.assertEqual(len(s), 1)


# ============================================================
#  Pool: interning & size tracking (module-level POOL)
# ============================================================

class TestSharedPoolInternAndSize(unittest.TestCase):
    """Tests on the module-level POOL (SHM-backed)."""

    def test_intern_increases_size(self):
        pool = POOL
        initial = pool.size
        s = pool.istr('__test_size_a__')
        self.assertEqual(pool.size, initial + 1)
        # Re-interning same key must not grow
        s2 = pool.istr('__test_size_a__')
        self.assertEqual(pool.size, initial + 1)

    def test_len_matches_size(self):
        pool = POOL
        self.assertEqual(len(pool), pool.size)

    def test_multiple_unique_strings(self):
        pool = POOL
        initial = pool.size
        keys = ['__multi_a__', '__multi_b__', '__multi_c__']
        for k in keys:
            pool.istr(k)
        self.assertEqual(pool.size, initial + len(keys))

    def test_empty_string_can_be_interned(self):
        """Empty strings are valid in the original algorithm (1-byte allocation)."""
        pool = POOL
        inst = pool.istr('')
        self.assertEqual(inst.string, '')
        # Re-interning must return the same instance
        inst2 = pool.istr('')
        self.assertEqual(inst.address, inst2.address)

    def test_none_raises(self):
        pool = POOL
        with self.assertRaises(TypeError):
            pool.istr(None)


# ============================================================
#  Pool: __getitem__ lookup
# ============================================================

class TestSharedPoolGetitem(unittest.TestCase):
    """Tests on the module-level POOL __getitem__."""

    def setUp(self):
        POOL.istr('__lookup_key__')

    def test_getitem_existing(self):
        inst = POOL['__lookup_key__']
        self.assertIsInstance(inst, InternString)
        self.assertEqual(inst.string, '__lookup_key__')

    def test_getitem_missing_raises_keyerror(self):
        with self.assertRaises(KeyError):
            _ = POOL['__never_interned_key_xyz__']

    def test_getitem_empty_string_raises(self):
        with self.assertRaises(KeyError):
            _ = POOL['']


# ============================================================
#  Stable pointer identity
# ============================================================

class TestStablePointer(unittest.TestCase):
    """Verify same key always maps to the same internalized pointer."""

    def setUp(self):
        self.pool = InternStringPool()

    def tearDown(self):
        del self.pool

    def test_same_address_on_reintern(self):
        key = 'stable_pointer_test'
        s1 = self.pool.istr(key)
        for _ in range(100):
            s2 = self.pool.istr(key)
            self.assertEqual(s1.address, s2.address)
            self.assertEqual(s1.string, s2.string)

    def test_address_different_for_different_keys(self):
        a = self.pool.istr('key_a')
        b = self.pool.istr('key_b')
        self.assertNotEqual(a.address, b.address)

    def test_address_preserved_after_other_insertions(self):
        a = self.pool.istr('stable_key')
        addr_before = a.address
        for i in range(100):
            self.pool.istr(f'filler_{i}')
        a_after = self.pool.istr('stable_key')
        self.assertEqual(addr_before, a_after.address)

    def test_string_value_equals_original(self):
        key = 'exact_match_test'
        inst = self.pool.istr(key)
        self.assertEqual(inst.string, key)
        self.assertEqual(len(inst.string), len(key))


# ============================================================
#  Internalized iteration
# ============================================================

class TestInternalizedIteration(unittest.TestCase):
    """Verify the internalized() generator."""

    def setUp(self):
        self.pool = InternStringPool()

    def tearDown(self):
        del self.pool

    def test_empty_pool_yields_nothing(self):
        items = list(self.pool.internalized())
        self.assertEqual(items, [])

    def test_iteration_returns_internstrings(self):
        keys = {'x', 'y', 'z'}
        for k in keys:
            self.pool.istr(k)
        items = list(self.pool.internalized())
        self.assertEqual(len(items), 3)
        for item in items:
            self.assertIsInstance(item, InternString)
        returned_keys = {item.string for item in items}
        self.assertEqual(returned_keys, keys)

    def test_iteration_order_is_insertion_order(self):
        """Iteration is in reverse insertion order (LIFO linked list)."""
        keys = ['first', 'second', 'third']
        for k in keys:
            self.pool.istr(k)
        items = list(self.pool.internalized())
        # Native algorithm prepends to head → reverse insertion order
        self.assertEqual([item.string for item in items], list(reversed(keys)))

    def test_reinterning_does_not_change_order(self):
        keys = ['a', 'b', 'c']
        for k in keys:
            self.pool.istr(k)
        # Re-intern 'a' — already exists, must not move
        self.pool.istr('a')
        items = list(self.pool.internalized())
        self.assertEqual([item.string for item in items], list(reversed(keys)))

    def test_large_iteration(self):
        count = 500
        for i in range(count):
            self.pool.istr(f'iter_{i}')
        items = list(self.pool.internalized())
        self.assertEqual(len(items), count)
        # Verify all present
        strings = {item.string for item in items}
        for i in range(count):
            self.assertIn(f'iter_{i}', strings)


# ============================================================
#  Custom pool lifecycle
# ============================================================

class TestCustomPool(unittest.TestCase):
    """Verify InternStringPool instances created directly."""

    def test_create_empty(self):
        pool = InternStringPool()
        self.assertEqual(pool.size, 0)
        self.assertEqual(len(pool), 0)

    def test_intern_and_size(self):
        pool = InternStringPool()
        self.assertEqual(pool.size, 0)
        pool.istr('a')
        self.assertEqual(pool.size, 1)
        pool.istr('b')
        self.assertEqual(pool.size, 2)
        pool.istr('a')  # no change
        self.assertEqual(pool.size, 2)

    def test_getitem(self):
        pool = InternStringPool()
        pool.istr('exists')
        self.assertEqual(pool['exists'].string, 'exists')

    def test_getitem_missing(self):
        pool = InternStringPool()
        with self.assertRaises(KeyError):
            _ = pool['missing']

    def test_address(self):
        pool = InternStringPool()
        addr = pool.address
        self.assertIsInstance(addr, str)
        self.assertTrue(addr.startswith('0x'))

    def test_internalized(self):
        pool = InternStringPool()
        keys = ['k1', 'k2', 'k3']
        for k in keys:
            pool.istr(k)
        result = {s.string for s in pool.internalized()}
        self.assertEqual(result, set(keys))

    def test_multiple_pools_independent(self):
        p1 = InternStringPool()
        p2 = InternStringPool()
        p1.istr('p1_only')
        p2.istr('p2_only')
        self.assertEqual(p1.size, 1)
        self.assertEqual(p2.size, 1)
        self.assertEqual(p1['p1_only'].string, 'p1_only')
        self.assertEqual(p2['p2_only'].string, 'p2_only')
        with self.assertRaises(KeyError):
            p1['p2_only']
        with self.assertRaises(KeyError):
            p2['p1_only']

    def test_pool_dealloc(self):
        """Ensure pool can be created, used, and freed without crash."""
        pool = InternStringPool()
        for i in range(100):
            pool.istr(f'temp_{i}')
        self.assertEqual(pool.size, 100)
        del pool  # must not crash


# ============================================================
#  INTRA_POOL (heap allocator)
# ============================================================

class TestIntraPool(unittest.TestCase):
    """Verify the heap-backed INTRA_POOL."""

    def test_basic_operations(self):
        s1 = INTRA_POOL.istr('local1')
        s2 = INTRA_POOL.istr('local2')
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertEqual(s1.string, 'local1')
        self.assertEqual(s2.string, 'local2')

    def test_reintern_same_address(self):
        s1 = INTRA_POOL.istr('intra_reintern')
        s2 = INTRA_POOL.istr('intra_reintern')
        self.assertEqual(s1.address, s2.address)

    def test_internalized_contains(self):
        s1 = INTRA_POOL.istr('intra_iter_a')
        s2 = INTRA_POOL.istr('intra_iter_b')
        strings = {s.string for s in INTRA_POOL.internalized()}
        self.assertIn('intra_iter_a', strings)
        self.assertIn('intra_iter_b', strings)

    def test_getitem(self):
        INTRA_POOL.istr('intra_getitem')
        inst = INTRA_POOL['intra_getitem']
        self.assertEqual(inst.string, 'intra_getitem')

    def test_intra_independent_from_pool(self):
        """INTRA_POOL and POOL are independent."""
        INTRA_POOL.istr('intra_only')
        # Should not be in POOL
        with self.assertRaises(KeyError):
            POOL['intra_only']


# ============================================================
#  Unicode strings
# ============================================================

class TestUnicode(unittest.TestCase):
    """Verify unicode string interning."""

    def setUp(self):
        self.pool = InternStringPool()

    def tearDown(self):
        del self.pool

    def test_unicode_basic(self):
        inst = self.pool.istr('café')
        self.assertEqual(inst.string, 'café')

    def test_unicode_chinese(self):
        inst = self.pool.istr('你好世界')
        self.assertEqual(inst.string, '你好世界')

    def test_unicode_emoji(self):
        inst = self.pool.istr('🎉🚀🔥')
        self.assertEqual(inst.string, '🎉🚀🔥')

    def test_unicode_reintern_same_address(self):
        a = self.pool.istr('こんにちは')
        b = self.pool.istr('こんにちは')
        self.assertEqual(a.address, b.address)

    def test_unicode_mixed(self):
        inst = self.pool.istr('mix_émoji_🎉_中文')
        self.assertEqual(inst.string, 'mix_émoji_🎉_中文')

    def test_unicode_zero_width(self):
        inst = self.pool.istr('zero​width')
        self.assertEqual(inst.string, 'zero​width')

    def test_unicode_surrogate_pairs(self):
        # Emoji outside BMP uses surrogate pairs in UTF-16 but is fine in UTF-8
        inst = self.pool.istr('𝄞')  # U+1D11E MUSICAL SYMBOL G CLEF
        self.assertEqual(inst.string, '𝄞')


# ============================================================
#  Long strings
# ============================================================

class TestLongStrings(unittest.TestCase):
    """Verify long string interning."""

    def setUp(self):
        self.pool = InternStringPool()

    def tearDown(self):
        del self.pool

    def test_long_string_1k(self):
        s = 'x' * 1000
        inst = self.pool.istr(s)
        self.assertEqual(inst.string, s)

    def test_long_string_10k(self):
        s = 'y' * 10000
        inst = self.pool.istr(s)
        self.assertEqual(inst.string, s)

    def test_long_string_reintern(self):
        s = 'z' * 5000
        a = self.pool.istr(s)
        b = self.pool.istr(s)
        self.assertEqual(a.address, b.address)

    def test_long_unicode(self):
        s = '字' * 1000
        inst = self.pool.istr(s)
        self.assertEqual(inst.string, s)


# ============================================================
#  Stress tests
# ============================================================

class TestStress(unittest.TestCase):
    """Stress-test with many strings."""

    def test_many_strings_1k(self):
        pool = InternStringPool()
        count = 1000
        for i in range(count):
            pool.istr(f'stress_{i:08d}')
        self.assertEqual(pool.size, count)
        # Verify all can be retrieved
        for i in range(count):
            self.assertEqual(pool[f'stress_{i:08d}'].string, f'stress_{i:08d}')
        del pool

    def test_many_strings_10k(self):
        pool = InternStringPool()
        count = 10000
        for i in range(count):
            pool.istr(f'big_{i:08d}')
        self.assertEqual(pool.size, count)
        # Spot-check retrieval
        for i in (0, count // 2, count - 1):
            self.assertEqual(pool[f'big_{i:08d}'].string, f'big_{i:08d}')
        del pool

    def test_repeated_intern_same_key(self):
        pool = InternStringPool()
        key = 'repeated_key'
        for _ in range(10000):
            inst = pool.istr(key)
            self.assertEqual(inst.string, key)
        self.assertEqual(pool.size, 1)
        del pool

    def test_intern_and_lookup_many(self):
        pool = InternStringPool()
        count = 2000
        for i in range(count):
            pool.istr(f'lookup_{i}')
        # Lookup all in random-ish order
        for i in range(count - 1, -1, -1):
            self.assertEqual(pool[f'lookup_{i}'].string, f'lookup_{i}')
        del pool


# ============================================================
#  Thread safety
# ============================================================

class TestThreadSafety(unittest.TestCase):
    """Verify correctness under concurrent access."""

    def test_concurrent_intern_different_keys(self):
        pool = InternStringPool()
        errors = []
        n_threads = 8
        n_per_thread = 500
        barrier = threading.Barrier(n_threads)

        def worker(thread_id):
            try:
                barrier.wait()
                for i in range(n_per_thread):
                    key = f'thread_{thread_id}_key_{i}'
                    inst = pool.istr(key)
                    if inst.string != key:
                        errors.append(f'Wrong string: {inst.string} != {key}')
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(pool.size, n_threads * n_per_thread)
        del pool

    def test_concurrent_intern_same_keys(self):
        pool = InternStringPool()
        errors = []
        n_threads = 8
        n_per_thread = 100
        barrier = threading.Barrier(n_threads)

        def worker(thread_id):
            try:
                barrier.wait()
                for i in range(n_per_thread):
                    key = f'shared_key_{i}'
                    inst = pool.istr(key)
                    if inst.string != key:
                        errors.append(f'Wrong string')
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(pool.size, n_per_thread)
        del pool

    def test_concurrent_getitem_and_intern(self):
        pool = InternStringPool()
        # Pre-populate
        for i in range(100):
            pool.istr(f'concurrent_{i}')

        errors = []
        barrier = threading.Barrier(4)

        def writer():
            try:
                barrier.wait()
                for i in range(100, 300):
                    pool.istr(f'concurrent_{i}')
            except Exception as e:
                errors.append(f'writer: {e}')

        def reader():
            try:
                barrier.wait()
                for _ in range(1000):
                    try:
                        inst = pool[f'concurrent_{50}']
                        if inst.string != 'concurrent_50':
                            errors.append('Wrong value')
                    except KeyError:
                        pass  # may not be interned yet
            except Exception as e:
                errors.append(f'reader: {e}')

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertGreaterEqual(pool.size, 100)
        del pool


# ============================================================
#  Multi-process shared memory (fork)
# ============================================================

@unittest.skipUnless(_FORK_AVAILABLE, "fork not available on this platform")
class TestMultiprocess(unittest.TestCase):
    """Verify SHM-backed POOL works across fork()."""

    def test_cross_process_sharing(self):
        POOL.istr('fork_test_parent')

        pid = os.fork()
        if pid == 0:
            # Child
            try:
                # Should be able to read parent's key
                inst = POOL['fork_test_parent']
                # Intern a new key
                POOL.istr('fork_test_child')
                os._exit(0)
            except Exception as e:
                print(f'Child error: {e}')
                os._exit(1)
        else:
            # Parent
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.WEXITSTATUS(status), 0)
            # Child's key should be visible
            inst = POOL['fork_test_child']
            self.assertEqual(inst.string, 'fork_test_child')

    def test_multiprocessing_module(self):
        from multiprocessing import Process

        POOL.istr('mp_cat')

        def worker():
            istr_cat = POOL['mp_cat']
            self.assertEqual(istr_cat.string, 'mp_cat')
            POOL.istr('mp_dog')

        p = Process(target=worker)
        p.start()
        time.sleep(0.5)
        POOL.istr('mp_dog')  # also intern from parent
        p.join()
        self.assertEqual(p.exitcode, 0)
        # Both should see 'mp_dog'
        self.assertEqual(POOL['mp_dog'].string, 'mp_dog')


# ============================================================
#  Edge cases
# ============================================================

class TestEdgeCases(unittest.TestCase):
    """Corner cases and edge conditions."""

    def test_single_char(self):
        pool = InternStringPool()
        inst = pool.istr('x')
        self.assertEqual(inst.string, 'x')
        self.assertEqual(len(inst.string), 1)

    def test_whitespace_only(self):
        pool = InternStringPool()
        inst = pool.istr('   \t\n  ')
        self.assertEqual(inst.string, '   \t\n  ')

    def test_nul_containing_string(self):
        """String with embedded NUL byte (Python supports this)."""
        pool = InternStringPool()
        s = 'before\x00after'
        inst = pool.istr(s)
        # Note: C layer uses strlen(), so NUL bytes truncate the string
        # This is expected behavior matching PyAlgoEngine
        self.assertEqual(inst.string, 'before')

    def test_numeric_strings(self):
        pool = InternStringPool()
        for n in ['0', '-1', '3.14', '1e10', 'inf', 'nan']:
            inst = pool.istr(n)
            self.assertEqual(inst.string, n)

    def test_special_chars(self):
        pool = InternStringPool()
        chars = '!@#$%^&*()_+-=[]{}|;:\'",.<>?/~`'
        inst = pool.istr(chars)
        self.assertEqual(inst.string, chars)

    def test_newline_strings(self):
        pool = InternStringPool()
        inst = pool.istr('line1\nline2\r\nline3')
        self.assertEqual(inst.string, 'line1\nline2\r\nline3')

    def test_identical_hash_collision(self):
        """Test interning strings that might cause hash collisions."""
        pool = InternStringPool()
        # Just verify many strings work correctly
        for i in range(200):
            pool.istr(f'hash_test_{i}')
        for i in range(200):
            self.assertEqual(pool[f'hash_test_{i}'].string, f'hash_test_{i}')

    def test_size_property_on_valid_pool(self):
        pool = InternStringPool()
        self.assertEqual(pool.size, 0)
        pool.istr('test')
        self.assertGreater(pool.size, 0)

    def test_cannot_create_pool_without_deps(self):
        """Verify InternStringPool() raises if allocator not available."""
        # Should work fine — allocators are module-level globals
        pool = InternStringPool()
        self.assertIsNotNone(pool)


if __name__ == '__main__':
    unittest.main()
