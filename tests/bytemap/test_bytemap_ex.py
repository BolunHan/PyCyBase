"""Test suite for ByteMapEx, ByteMapExDouble, BoundByteMapEx, BoundByteMapExDouble.

Port of Quark test_10_c_bytemapex.py, adapted for PyCyBase.
"""
import math
import time
import unittest

from cbase.bytemap.c_bytemap import (
    _ByteMapBase,
    _BoundByteMapBase,
    BoundByteMap,
    BoundByteMapEx,
    BoundByteMapExDouble,
    BoundByteSet,
    ByteMap,
    ByteMapEx,
    ByteMapExDouble,
)


class TestByteMapEx(unittest.TestCase):
    """Contract:
    - Key/value CRUD behaves like a mapping over str -> bytes.
    - Iteration, view helpers, and derived representations are consistent.
    - Missing-key behavior matches dict-like semantics for get/pop.
    """

    def setUp(self):
        self.mapping = ByteMapEx(slot_capacity=32)

    def test_00_basic_set_get_len_contains(self):
        self.mapping["alpha"] = b"A"
        self.assertEqual(self.mapping["alpha"], b"A")
        self.assertEqual(len(self.mapping), 1)
        self.assertIn("alpha", self.mapping)
        self.assertTrue(self.mapping.contains("alpha"))

    def test_01_get_and_pop_missing_contract(self):
        self.assertIsNone(self.mapping.get("missing"))
        self.assertEqual(self.mapping.get("missing", b"fallback"), b"fallback")
        self.assertEqual(self.mapping.pop("missing", b"fallback"), b"fallback")
        with self.assertRaises(KeyError):
            self.mapping.pop("missing")

    def test_02_keys_values_items_as_dict_consistency(self):
        payload = {"a": b"1", "b": b"22", "c": b"333"}
        for key, value in payload.items():
            self.mapping[key] = value

        self.assertEqual(set(self.mapping.keys()), set(payload.keys()))
        self.assertEqual(self.mapping.as_dict, payload)
        self.assertEqual(dict(self.mapping.items()), payload)
        self.assertEqual(set(self.mapping.values()), set(payload.values()))
        self.assertEqual(set(iter(self.mapping)), set(payload.keys()))

    def test_03_clear_resets_size(self):
        self.mapping["x"] = b"v"
        self.mapping["y"] = b"w"
        self.assertGreater(self.mapping.size, 0)

        self.mapping.clear()

        self.assertEqual(len(self.mapping), 0)
        self.assertEqual(self.mapping.size, 0)
        self.assertEqual(self.mapping.as_dict, {})

    def test_04_fork_shares_storage(self):
        self.mapping["root"] = b"r"
        view = self.mapping.fork()

        view["child"] = b"c"

        self.assertEqual(self.mapping["child"], b"c")
        self.assertEqual(view["root"], b"r")

    def test_05_copy_creates_independent_clone(self):
        self.mapping["a"] = b"1"
        self.mapping["b"] = b"2"

        import copy
        clone = copy.copy(self.mapping)
        self.assertEqual(clone["a"], b"1")
        self.assertEqual(clone["b"], b"2")

        # Modify original
        self.mapping["a"] = b"111"
        # Clone should be unaffected
        self.assertEqual(clone["a"], b"1")

        del clone

    def test_06_iteration_order(self):
        keys = ["z", "a", "m", "b"]
        for k in keys:
            self.mapping[k] = k.encode()

        iter_keys = list(self.mapping)
        self.assertEqual(iter_keys, keys)

    def test_07_slot_capacity_enforced(self):
        # Setting a value larger than slot_capacity should raise
        with self.assertRaises(RuntimeError):
            self.mapping["big"] = b"x" * 100  # slot_capacity is 32


class TestByteMapExDouble(unittest.TestCase):
    """Contract:
    - Mapping behaves as str -> double.
    - Numeric APIs return doubles consistently.
    - Missing-key behavior mirrors dict-style defaults and KeyError semantics.
    """

    def setUp(self):
        self.mapping = ByteMapExDouble()

    @staticmethod
    def _build_payload(size):
        return {f"k_{i:05d}": (i * 0.125) - 17.0 for i in range(size)}

    def test_00_basic_set_get_and_contains(self):
        self.mapping["px"] = 12.5
        self.assertAlmostEqual(self.mapping["px"], 12.5)
        self.assertEqual(len(self.mapping), 1)
        self.assertIn("px", self.mapping)
        self.assertTrue(self.mapping.contains("px"))

    def test_01_get_default_nan_and_custom_default(self):
        nan_value = self.mapping.get("missing")
        self.assertTrue(math.isnan(nan_value))
        self.assertAlmostEqual(self.mapping.get("missing", 7.25), 7.25)

    def test_02_pop_returns_double_and_removes_key(self):
        self.mapping["k1"] = 3.14

        popped = self.mapping.pop("k1")

        self.assertAlmostEqual(popped, 3.14)
        self.assertNotIn("k1", self.mapping)

    def test_03_pop_missing_contract(self):
        self.assertAlmostEqual(self.mapping.pop("missing", 9.0), 9.0)
        with self.assertRaises(KeyError):
            self.mapping.pop("missing")

    def test_04_values_items_as_dict_are_numeric(self):
        payload = {"x": 1.5, "y": 2.5, "z": -3.0}
        for key, value in payload.items():
            self.mapping[key] = value

        self.assertEqual(set(self.mapping.keys()), set(payload.keys()))
        self.assertEqual(self.mapping.as_dict, payload)
        self.assertEqual(dict(self.mapping.items()), payload)
        self.assertEqual(set(self.mapping.values()), set(payload.values()))

    def test_05_bulk_set_get_contains_and_overwrite(self):
        payload = self._build_payload(256)
        for key, value in payload.items():
            self.mapping[key] = value

        self.assertEqual(len(self.mapping), len(payload))
        for key, value in payload.items():
            self.assertIn(key, self.mapping)
            self.assertTrue(self.mapping.contains(key))
            self.assertAlmostEqual(self.mapping[key], value)

        updated = {key: value + 10.0 for index, (key, value) in enumerate(payload.items()) if index % 7 == 0}
        for key, value in updated.items():
            self.mapping[key] = value
            payload[key] = value

        self.assertEqual(len(self.mapping), len(payload))
        for key, value in payload.items():
            self.assertAlmostEqual(self.mapping[key], value)

    def test_06_bulk_pop_preserves_remaining_entries(self):
        payload = self._build_payload(192)
        for key, value in payload.items():
            self.mapping[key] = value

        pop_keys = [key for index, key in enumerate(payload) if index % 3 == 0]
        kept = dict(payload)
        for key in pop_keys:
            expected = payload[key]
            popped = self.mapping.pop(key)
            self.assertAlmostEqual(popped, expected)
            del kept[key]

        self.assertEqual(len(self.mapping), len(kept))
        for key, value in kept.items():
            self.assertAlmostEqual(self.mapping[key], value)
        for key in pop_keys:
            self.assertAlmostEqual(self.mapping.pop(key, -999.0), -999.0)
            with self.assertRaises(KeyError):
                self.mapping.pop(key)

    def test_07_rehash_and_auto_extend(self):
        mapping = ByteMapExDouble(init_capacity=2)

        for i in range(1_000):
            key = f"key_{i:05d}"
            value = float(i + .25)
            mapping[key] = value

        for i in range(1_000):
            key = f"key_{i:05d}"
            expected = float(i + .25)
            self.assertAlmostEqual(mapping[key], expected)

    def test_08_copy(self):
        self.mapping["a"] = 1.0
        self.mapping["b"] = 2.0

        import copy
        clone = copy.copy(self.mapping)
        self.assertAlmostEqual(clone["a"], 1.0)
        self.assertAlmostEqual(clone["b"], 2.0)

        self.mapping["a"] = 10.0
        self.assertAlmostEqual(clone["a"], 1.0)

        del clone


class TestBoundByteMapEx(unittest.TestCase):
    """Contract:
    - BoundByteMapEx keeps Python dict cache and C storage consistent for CRUD operations.
    - Forked/rebound instances stay synchronized through callback-based updates.
    - Error behavior is explicit for invalid key/value types and missing-key operations.
    """

    def setUp(self):
        self.mapping = BoundByteMapEx(slot_capacity=64)

    @staticmethod
    def _build_payload(size):
        return {f"bk_{i:05d}": f"value_{i:05d}".encode() for i in range(size)}

    def test_00_bulk_set_get_contains_and_overwrite(self):
        payload = self._build_payload(256)
        for key, value in payload.items():
            self.mapping[key] = value

        self.assertEqual(len(self.mapping), len(payload))
        for key, value in payload.items():
            self.assertIn(key, self.mapping)
            self.assertEqual(self.mapping[key], value)

        updated = {key: value + b"_u" for idx, (key, value) in enumerate(payload.items()) if idx % 5 == 0}
        for key, value in updated.items():
            self.mapping[key] = value
            payload[key] = value

        self.assertEqual(len(self.mapping), len(payload))
        self.assertEqual(dict(self.mapping), payload)

    def test_01_pop_and_setdefault_contract(self):
        payload = self._build_payload(96)
        self.mapping.update(payload)

        pop_keys = [key for idx, key in enumerate(payload) if idx % 4 == 0]
        kept = dict(payload)
        for key in pop_keys:
            self.assertEqual(self.mapping.pop(key), payload[key])
            del kept[key]

        self.assertEqual(dict(self.mapping), kept)
        self.assertEqual(self.mapping.pop("missing", b"fallback"), b"fallback")
        with self.assertRaises(KeyError):
            self.mapping.pop("missing")

        existing_key = next(iter(kept))
        self.assertEqual(self.mapping.setdefault(existing_key, b"new"), kept[existing_key])
        self.assertEqual(self.mapping[existing_key], kept[existing_key])

        self.assertEqual(self.mapping.setdefault("new_key", b"new_value"), b"new_value")
        self.assertEqual(self.mapping["new_key"], b"new_value")
        with self.assertRaises(KeyError):
            self.mapping.setdefault("missing_without_default")

    def test_02_update_clear_and_repr(self):
        self.mapping.update({"a": b"1", "b": b"2"})
        self.mapping.update(c=b"3", d=b"4")

        self.assertEqual(
            dict(self.mapping),
            {"a": b"1", "b": b"2", "c": b"3", "d": b"4"},
        )

        rep = repr(self.mapping)
        self.assertIn("BoundByteMapEx", rep)
        self.assertIn("a", rep)

        self.mapping.clear()
        self.assertEqual(len(self.mapping), 0)
        self.assertEqual(dict(self.mapping), {})

    def test_03_fork_keeps_bidirectional_sync(self):
        payload = self._build_payload(64)
        self.mapping.update(payload)
        sibling = self.mapping.fork()

        self.assertEqual(dict(sibling), payload)

        self.mapping["left"] = b"L"
        self.assertEqual(sibling["left"], b"L")

        sibling["right"] = b"R"
        self.assertEqual(self.mapping["right"], b"R")

        popped = sibling.pop("bk_00000")
        self.assertEqual(popped, payload["bk_00000"])
        self.assertNotIn("bk_00000", self.mapping)

        self.mapping.clear()
        self.assertEqual(dict(self.mapping), {})
        self.assertEqual(dict(sibling), {})

    def test_04_rebind_syncs_to_new_source(self):
        src_raw = ByteMapEx(slot_capacity=64)
        for i in range(48):
            src_raw[f"raw_{i:03d}"] = f"rv_{i:03d}".encode()

        self.mapping.update({"legacy": b"old", "stale": b"data"})
        self.mapping.rebind(src_raw)
        self.assertEqual(dict(self.mapping), src_raw.as_dict)

        src_raw["raw_new"] = b"new"
        self.assertEqual(self.mapping["raw_new"], b"new")

        src_raw.pop("raw_000")
        self.assertNotIn("raw_000", self.mapping)

        src_bound = BoundByteMapEx(slot_capacity=64)
        src_bound.update({"bound_1": b"v1", "bound_2": b"v2", "bound_3": b"v3"})
        self.mapping.rebind(src_bound)
        self.assertEqual(dict(self.mapping), dict(src_bound))

        src_bound["bound_4"] = b"v4"
        self.assertEqual(self.mapping["bound_4"], b"v4")

        src_bound.pop("bound_1")
        self.assertNotIn("bound_1", self.mapping)

        src_bound.clear()
        self.assertEqual(dict(self.mapping), {})

    def test_05_invalid_key_value_types_raise(self):
        with self.assertRaises(TypeError):
            self.mapping[1] = b"x"

        with self.assertRaises(TypeError):
            self.mapping["good_key"] = "not-bytes"

        with self.assertRaises(TypeError):
            self.mapping.pop(1)

    def test_06_sync_method(self):
        self.mapping["a"] = b"1"
        self.mapping["b"] = b"2"

        # sync should refresh from C storage (no-op for consistent state)
        self.mapping.sync("a")
        self.assertEqual(self.mapping["a"], b"1")

    def test_07_freed_clears_bound_view(self):
        src = BoundByteMapEx(slot_capacity=64)
        src["keep"] = b"me"
        view = src.fork()

        self.assertIn("keep", view)
        del src
        import gc
        gc.collect()
        self.assertFalse(bool(view))


class TestBoundByteMapExDouble(unittest.TestCase):
    """Contract:
    - BoundByteMapExDouble keeps Python dict cache and C storage consistent for float-like values.
    - Forked/rebound instances must reflect callback-driven mutations.
    - Coercion and failure modes are explicit.
    """

    def setUp(self):
        self.mapping = BoundByteMapExDouble()

    @staticmethod
    def _build_payload(size):
        return {f"dk_{i:05d}": (i * 0.5) - 37.25 for i in range(size)}

    def assert_float_mapping_matches(self, mapping, expected):
        self.assertEqual(set(mapping.keys()), set(expected.keys()))
        self.assertEqual(len(mapping), len(expected))
        for key, expected_value in expected.items():
            self.assertIn(key, mapping)
            self.assertIsInstance(mapping[key], float)
            self.assertAlmostEqual(mapping[key], expected_value)

    def test_00_bulk_set_get_contains_and_overwrite(self):
        payload = self._build_payload(256)
        for key, value in payload.items():
            self.mapping[key] = value

        self.assert_float_mapping_matches(self.mapping, payload)

        updated = {key: value + 11.75 for index, (key, value) in enumerate(payload.items()) if index % 5 == 0}
        for key, value in updated.items():
            self.mapping[key] = value
            payload[key] = value

        self.assert_float_mapping_matches(self.mapping, payload)

    def test_01_fork(self):
        src = BoundByteMapExDouble()
        payload = self._build_payload(128)
        src.update(payload)
        forked = src.fork()

        self.assertEqual(len(forked), len(payload))
        for key, expected in payload.items():
            self.assertIn(key, forked)
            self.assertIsInstance(forked[key], float)
            self.assertAlmostEqual(forked[key], expected)

    def test_02_pop_default_and_remaining_entries_contract(self):
        payload = self._build_payload(128)
        self.mapping.update(payload)

        pop_keys = [key for index, key in enumerate(payload) if index % 4 == 0]
        kept = dict(payload)
        for key in pop_keys:
            self.assertAlmostEqual(self.mapping.pop(key), payload[key])
            del kept[key]

        self.assert_float_mapping_matches(self.mapping, kept)
        self.assertAlmostEqual(self.mapping.pop("missing", 7.5), 7.5)
        with self.assertRaises(KeyError):
            self.mapping.pop("missing")

    def test_03_update_clear_and_repr_numeric_state(self):
        payload = {"a": 1.25, "b": -2.5, "c": math.pi, "d": 0.0}
        self.mapping.update(payload)

        self.assert_float_mapping_matches(self.mapping, payload)

        rep = repr(self.mapping)
        self.assertIn("BoundByteMapExDouble", rep)
        self.assertIn("a", rep)

        self.mapping.clear()
        self.assertEqual(len(self.mapping), 0)
        self.assertEqual(dict(self.mapping), {})

    def test_04_fork_keeps_bidirectional_numeric_sync(self):
        payload = self._build_payload(64)
        self.mapping.update(payload)
        sibling = self.mapping.fork()

        self.assert_float_mapping_matches(sibling, payload)

        self.mapping["sentinel_pi"] = math.pi
        self.mapping["sentinel_neg_zero"] = -0.0
        self.assertAlmostEqual(sibling["sentinel_pi"], math.pi)
        self.assertEqual(sibling["sentinel_neg_zero"], 0.0)
        self.assertEqual(math.copysign(1.0, sibling["sentinel_neg_zero"]), -1.0)

        sibling["sentinel_small"] = 1e-12
        sibling["dk_00001"] = -123.75
        self.assertAlmostEqual(self.mapping["sentinel_small"], 1e-12)
        self.assertAlmostEqual(self.mapping["dk_00001"], -123.75)

        popped = sibling.pop("dk_00000")
        self.assertAlmostEqual(popped, payload["dk_00000"])
        self.assertNotIn("dk_00000", self.mapping)

        self.mapping.clear()
        self.assertEqual(dict(self.mapping), {})
        self.assertEqual(dict(sibling), {})

    def test_05_rebind_to_bytemapexdouble_replaces_state_and_tracks_source(self):
        src_raw = ByteMapExDouble()
        expected = self._build_payload(48)
        for key, value in expected.items():
            src_raw[key] = value

        self.mapping.update({"stale_a": 99.0, "stale_b": -11.0})
        self.mapping.rebind(src_raw)
        self.assert_float_mapping_matches(self.mapping, expected)
        self.assertNotIn("stale_a", self.mapping)
        self.assertNotIn("stale_b", self.mapping)

        src_raw["fresh"] = 1e12
        expected["fresh"] = 1e12
        self.assertAlmostEqual(self.mapping["fresh"], 1e12)

        src_raw["dk_00010"] = -222.5
        expected["dk_00010"] = -222.5
        self.assertAlmostEqual(self.mapping["dk_00010"], -222.5)

        src_raw.pop("dk_00000")
        del expected["dk_00000"]
        self.assertNotIn("dk_00000", self.mapping)

        self.assert_float_mapping_matches(self.mapping, expected)

        src_raw.clear()
        self.assertEqual(dict(self.mapping), {})

    def test_06_rebind_to_bound_source_keeps_callback_sync(self):
        src_bound = BoundByteMapExDouble()
        expected = {"p0": 0.1, "p1": -2.5, "p2": math.pi, "p3": 5.5}
        src_bound.update(expected)

        self.mapping.update({"legacy": 7.0})
        self.mapping.rebind(src_bound)
        self.assert_float_mapping_matches(self.mapping, expected)
        self.assertNotIn("legacy", self.mapping)

        src_bound["p4"] = 1e-9
        expected["p4"] = 1e-9
        self.assertAlmostEqual(self.mapping["p4"], 1e-9)

        src_bound["p1"] = -7.25
        expected["p1"] = -7.25
        self.assertAlmostEqual(self.mapping["p1"], -7.25)

        popped = src_bound.pop("p0")
        self.assertAlmostEqual(popped, 0.1)
        del expected["p0"]
        self.assertNotIn("p0", self.mapping)

        self.assert_float_mapping_matches(self.mapping, expected)

        src_bound.clear()
        self.assertEqual(dict(self.mapping), {})

    def test_07_numeric_regression_values_survive_callback_paths(self):
        source = BoundByteMapExDouble()
        sentinel_values = {
            "zero": 0.0,
            "neg_zero": -0.0,
            "decimal": 0.1,
            "negative": -2.5,
            "pi": math.pi,
            "tiny": 1e-12,
            "huge": 1e12,
        }
        source.update(sentinel_values)
        observer = source.fork()

        for key, expected in sentinel_values.items():
            self.assertIsInstance(observer[key], float)
            self.assertAlmostEqual(observer[key], expected)

        rebound = BoundByteMapExDouble()
        rebound.rebind(source)
        for key, expected in sentinel_values.items():
            self.assertIsInstance(rebound[key], float)
            self.assertAlmostEqual(rebound[key], expected)

        self.assertEqual(observer["neg_zero"], 0.0)
        self.assertEqual(math.copysign(1.0, observer["neg_zero"]), -1.0)
        self.assertEqual(rebound["neg_zero"], 0.0)
        self.assertEqual(math.copysign(1.0, rebound["neg_zero"]), -1.0)

    def test_08_value_coercion_and_invalid_inputs(self):
        self.mapping["from_int"] = 1
        self.mapping["from_bool"] = True
        self.assertEqual(self.mapping["from_int"], 1.0)
        self.assertEqual(self.mapping["from_bool"], 1.0)

        with self.assertRaises(ValueError):
            self.mapping["bad_str"] = "abc"

        with self.assertRaises(TypeError):
            self.mapping["bad_obj"] = object()

        with self.assertRaises(TypeError):
            self.mapping[1] = 3.0

        with self.assertRaises(TypeError):
            self.mapping.pop(1)

        with self.assertRaises(TypeError):
            self.mapping.rebind({})


class TestByteMapExPatchedBehavior(unittest.TestCase):
    """Contract:
    - Existing-key updates should not grow capacity at threshold.
    - Tombstone reuse should not grow capacity at threshold.
    - Fresh-slot insertion at threshold may grow capacity safely.
    """

    def setUp(self):
        self.mapping = ByteMapExDouble(init_capacity=16)

    @staticmethod
    def _find_collision_key_for_ex(mapping, base_key, capacity):
        probe = ByteMap(init_capacity=capacity)
        probe.salt = mapping.salt
        target_bucket = probe.hash(base_key) % capacity
        for i in range(1, 200000):
            candidate = f"{base_key}#col#{i:06d}"
            if candidate == base_key:
                continue
            if probe.hash(candidate) % capacity == target_bucket:
                return candidate
        raise AssertionError("Failed to find colliding key for ByteMapExDouble tombstone test")

    def test_00_update_existing_at_threshold_does_not_rehash(self):
        initial_capacity = self.mapping.capacity
        n = initial_capacity // 2

        for i in range(n):
            self.mapping[f"k_{i:03d}"] = float(i)

        cap_before_update = self.mapping.capacity
        self.assertEqual(cap_before_update, initial_capacity)
        self.assertEqual(self.mapping.occupied, n)

        for i in range(n):
            self.mapping[f"k_{i:03d}"] = float(i) + 1000.0

        self.assertEqual(self.mapping.capacity, cap_before_update)
        self.assertEqual(self.mapping.size, n)
        self.assertEqual(self.mapping.occupied, n)
        for i in range(n):
            self.assertAlmostEqual(self.mapping[f"k_{i:03d}"], float(i) + 1000.0)

    def test_01_tombstone_reuse_at_threshold_does_not_rehash(self):
        for mode in ("same_key", "hash_collision"):
            with self.subTest(mode=mode):
                mapping = ByteMapExDouble(init_capacity=16)
                initial_capacity = mapping.capacity
                n = initial_capacity // 2

                for i in range(n):
                    mapping[f"k_{i:03d}"] = float(i)

                victim_key = "k_000"
                mapping.pop(victim_key)
                cap_before_insert = mapping.capacity
                occupied_before_insert = mapping.occupied

                if mode == "same_key":
                    insert_key = victim_key
                else:
                    insert_key = self._find_collision_key_for_ex(mapping, victim_key, cap_before_insert)

                mapping[insert_key] = 999.5

                self.assertEqual(mapping.capacity, cap_before_insert)
                self.assertEqual(mapping.occupied, occupied_before_insert)
                self.assertEqual(mapping.size, n)
                self.assertAlmostEqual(mapping[insert_key], 999.5)

    def test_02_fresh_slot_insert_at_threshold_can_grow(self):
        initial_capacity = self.mapping.capacity
        n = initial_capacity // 2

        for i in range(n):
            self.mapping[f"k_{i:03d}"] = float(i)

        self.mapping["k_extra"] = -0.25

        self.assertGreaterEqual(self.mapping.capacity, initial_capacity)
        self.assertIn("k_extra", self.mapping)
        for i in range(n):
            self.assertIn(f"k_{i:03d}", self.mapping)


class TestByteMapExVsByteMapConsistency(unittest.TestCase):
    """Test that ByteMap and ByteMapEx behave consistently since they share the same backend."""

    def test_shared_backend_layout(self):
        """ByteMap and ByteMapEx both work correctly."""
        bmap = ByteMap()
        value = object()
        bmap['test'] = value
        self.assertIs(bmap['test'], value)

        bmapex = ByteMapEx(slot_capacity=32)
        bmapex['test'] = b'hello'
        self.assertEqual(bmapex['test'], b'hello')


class TestByteMapClassHierarchy(unittest.TestCase):
    """Validate the class hierarchy: all ByteMap variants share _ByteMapBase as common base,
    and are PEERS (not ancestors) of each other."""

    def test_00_ByteMapBase_is_base_of_all(self):
        """_ByteMapBase is the common abstract base for all ByteMap variants."""
        self.assertTrue(issubclass(ByteMapEx, _ByteMapBase))
        self.assertTrue(issubclass(ByteMapExDouble, _ByteMapBase))
        self.assertTrue(issubclass(ByteMap, _ByteMapBase))

    def test_01_ByteMapEx_not_subclass_of_ByteMap(self):
        """ByteMapEx is NOT a subclass of ByteMap — they are peers."""
        self.assertFalse(issubclass(ByteMapEx, ByteMap))

    def test_02_ByteMap_not_subclass_of_ByteMapEx(self):
        """ByteMap is NOT a subclass of ByteMapEx — they are peers."""
        self.assertFalse(issubclass(ByteMap, ByteMapEx))

    def test_03_ByteMapExDouble_not_subclass_of_ByteMapEx(self):
        """ByteMapExDouble is NOT a subclass of ByteMapEx — they are peers."""
        self.assertFalse(issubclass(ByteMapExDouble, ByteMapEx))

    def test_04_ByteMapExDouble_not_subclass_of_ByteMap(self):
        """ByteMapExDouble is NOT a subclass of ByteMap — they are peers."""
        self.assertFalse(issubclass(ByteMapExDouble, ByteMap))

    def test_05_ByteMap_not_subclass_of_ByteMapExDouble(self):
        """ByteMap is NOT a subclass of ByteMapExDouble — they are peers."""
        self.assertFalse(issubclass(ByteMap, ByteMapExDouble))

    def test_06_isinstance_checks(self):
        """isinstance works correctly for all variants against _ByteMapBase."""
        bm_ex = ByteMapEx(slot_capacity=16)
        bm_ex_dbl = ByteMapExDouble()
        bm = ByteMap()

        self.assertIsInstance(bm_ex, _ByteMapBase)
        self.assertIsInstance(bm_ex_dbl, _ByteMapBase)
        self.assertIsInstance(bm, _ByteMapBase)

        # Cross-checks: peers are NOT instances of each other
        self.assertNotIsInstance(bm_ex, ByteMap)
        self.assertNotIsInstance(bm, ByteMapEx)
        self.assertNotIsInstance(bm_ex_dbl, ByteMapEx)
        self.assertNotIsInstance(bm_ex_dbl, ByteMap)


class TestBoundByteMapClassHierarchy(unittest.TestCase):
    """Validate the class hierarchy: all BoundByteMap variants share _BoundByteMapBase,
    and are PEERS of each other. BoundByteSet uses the same naming skeleton."""

    def test_00_BoundByteMapBase_is_base_of_all_dict_variants(self):
        """_BoundByteMapBase is the common abstract base for all bound dict variants."""
        self.assertTrue(issubclass(BoundByteMapEx, _BoundByteMapBase))
        self.assertTrue(issubclass(BoundByteMapExDouble, _BoundByteMapBase))
        self.assertTrue(issubclass(BoundByteMap, _BoundByteMapBase))

    def test_01_BoundByteSet_not_dict_variant(self):
        """BoundByteSet is NOT a subclass of _BoundByteMapBase (it's a set, not dict)."""
        self.assertFalse(issubclass(BoundByteSet, _BoundByteMapBase))

    def test_02_BoundByteMapEx_not_subclass_of_BoundByteMap(self):
        """BoundByteMapEx is NOT a subclass of BoundByteMap — they are peers."""
        self.assertFalse(issubclass(BoundByteMapEx, BoundByteMap))

    def test_03_BoundByteMap_not_subclass_of_BoundByteMapEx(self):
        """BoundByteMap is NOT a subclass of BoundByteMapEx — they are peers."""
        self.assertFalse(issubclass(BoundByteMap, BoundByteMapEx))

    def test_04_BoundByteMapExDouble_not_subclass_of_BoundByteMapEx(self):
        """BoundByteMapExDouble is NOT a subclass of BoundByteMapEx — they are peers."""
        self.assertFalse(issubclass(BoundByteMapExDouble, BoundByteMapEx))

    def test_05_BoundByteMapExDouble_not_subclass_of_BoundByteMap(self):
        """BoundByteMapExDouble is NOT a subclass of BoundByteMap — they are peers."""
        self.assertFalse(issubclass(BoundByteMapExDouble, BoundByteMap))

    def test_06_all_bound_variants_extend_dict(self):
        """All bound dict variants are dict subclasses."""
        self.assertTrue(issubclass(BoundByteMapEx, dict))
        self.assertTrue(issubclass(BoundByteMapExDouble, dict))
        self.assertTrue(issubclass(BoundByteMap, dict))

    def test_07_BoundByteSet_has_same_skeleton_naming(self):
        """BoundByteSet uses c_serialize_key / c_deserialize_key naming convention."""
        # Verify the methods exist (they are cdef, so we test indirectly)
        bset = BoundByteSet()
        bset.add('test_key')
        self.assertIn('test_key', bset)
        bset.discard('test_key')
        self.assertNotIn('test_key', bset)

    def test_08_isinstance_checks(self):
        """isinstance works correctly for all bound variants against _BoundByteMapBase."""
        bbm_ex = BoundByteMapEx(slot_capacity=64)
        bbm_ex_dbl = BoundByteMapExDouble()
        bbm = BoundByteMap()

        self.assertIsInstance(bbm_ex, _BoundByteMapBase)
        self.assertIsInstance(bbm_ex_dbl, _BoundByteMapBase)
        self.assertIsInstance(bbm, _BoundByteMapBase)

        # Cross-checks: peers are NOT instances of each other
        self.assertNotIsInstance(bbm_ex, BoundByteMap)
        self.assertNotIsInstance(bbm, BoundByteMapEx)
        self.assertNotIsInstance(bbm_ex_dbl, BoundByteMapEx)
        self.assertNotIsInstance(bbm_ex_dbl, BoundByteMap)

    def test_09_rebind_uses_common_base_type_check(self):
        """rebind() accepts any _ByteMapBase or _BoundByteMapBase instance."""
        src_map = ByteMap()
        src_map['a'] = 1
        bbm = BoundByteMap()
        bbm.rebind(src_map)  # rebind uses isinstance check against base classes
        self.assertEqual(bbm['a'], 1)


if __name__ == '__main__':
    unittest.main()
