"""Test suite for pylong 128-bit integer backports.

Contract: pylong_from_uint128 / pylong_from_int128 / pylong_as_uint128 /
pylong_as_int128 convert between Python int and 16-byte little-endian
128-bit integer representations.

Oracle: Python's built-in int.to_bytes / int.from_bytes with matching
byte order and signedness flags.
"""
import unittest

from cbase.backports.pylong import _INT128_MAX, _INT128_MIN, _UINT128_MAX, pylong_as_int128, pylong_as_uint128, pylong_from_int128, pylong_from_uint128

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UINT128_MAX = _UINT128_MAX
INT128_MAX = _INT128_MAX
INT128_MIN = _INT128_MIN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uint128_oracle(val: int) -> bytes:
    """Oracle: convert int → uint128_t bytes using stdlib."""
    return val.to_bytes(16, 'little', signed=False)


def _int128_oracle(val: int) -> bytes:
    """Oracle: convert int → int128_t bytes using stdlib."""
    return val.to_bytes(16, 'little', signed=True)


def _from_uint128_oracle(data: bytes) -> int:
    """Oracle: convert uint128_t bytes → int using stdlib."""
    return int.from_bytes(data, 'little', signed=False)


def _from_int128_oracle(data: bytes) -> int:
    """Oracle: convert int128_t bytes → int using stdlib."""
    return int.from_bytes(data, 'little', signed=True)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestUnsignedRoundTrip(unittest.TestCase):
    """Contract: pylong_as_uint128 followed by pylong_from_uint128 is identity
    for any valid uint128_t value."""

    def test_00_zero(self) -> None:
        """Zero round-trips correctly."""
        self.assertEqual(pylong_from_uint128(pylong_as_uint128(0)), 0)

    def test_01_one(self) -> None:
        """One round-trips correctly."""
        self.assertEqual(pylong_from_uint128(pylong_as_uint128(1)), 1)

    def test_02_max_value(self) -> None:
        """UINT128_MAX round-trips correctly."""
        val = UINT128_MAX
        result = pylong_from_uint128(pylong_as_uint128(val))
        self.assertEqual(result, val)

    def test_03_powers_of_two(self) -> None:
        """Powers of two up to 2**127 round-trip correctly."""
        for exp in range(0, 128):
            val = 1 << exp
            with self.subTest(exp=exp):
                self.assertEqual(
                    pylong_from_uint128(pylong_as_uint128(val)), val
                )

    def test_04_mid_range_values(self) -> None:
        """Arbitrary mid-range values round-trip correctly."""
        values = [
            0xDEADBEEFCAFEBABE,
            0x123456789ABCDEF0,
            UINT128_MAX // 2,
            UINT128_MAX // 3,
            (1 << 64) - 1,
            1 << 64,
            (1 << 96) - 1,
            1 << 96,
        ]
        for val in values:
            with self.subTest(val=hex(val)):
                self.assertEqual(
                    pylong_from_uint128(pylong_as_uint128(val)), val
                )

    def test_05_output_is_16_bytes(self) -> None:
        """pylong_as_uint128 always returns exactly 16 bytes."""
        values = [0, 1, 255, 256, (1 << 64) - 1, UINT128_MAX]
        for val in values:
            with self.subTest(val=val):
                result = pylong_as_uint128(val)
                self.assertIsInstance(result, bytes)
                self.assertEqual(len(result), 16)


class TestSignedRoundTrip(unittest.TestCase):
    """Contract: pylong_as_int128 followed by pylong_from_int128 is identity
    for any valid int128_t value."""

    def test_00_zero(self) -> None:
        """Zero round-trips correctly."""
        self.assertEqual(pylong_from_int128(pylong_as_int128(0)), 0)

    def test_01_positive_one(self) -> None:
        """+1 round-trips correctly."""
        self.assertEqual(pylong_from_int128(pylong_as_int128(1)), 1)

    def test_02_negative_one(self) -> None:
        """-1 round-trips correctly (two's complement)."""
        self.assertEqual(pylong_from_int128(pylong_as_int128(-1)), -1)

    def test_03_int128_max(self) -> None:
        """INT128_MAX round-trips correctly."""
        val = INT128_MAX
        result = pylong_from_int128(pylong_as_int128(val))
        self.assertEqual(result, val)

    def test_04_int128_min(self) -> None:
        """INT128_MIN round-trips correctly."""
        val = INT128_MIN
        result = pylong_from_int128(pylong_as_int128(val))
        self.assertEqual(result, val)

    def test_05_powers_of_two(self) -> None:
        """Powers of two (positive and negative) round-trip correctly."""
        for exp in range(0, 127):
            for sign in (1, -1):
                val = sign * (1 << exp)
                with self.subTest(val=val):
                    self.assertEqual(
                        pylong_from_int128(pylong_as_int128(val)), val
                    )

    def test_06_mid_range_values(self) -> None:
        """Arbitrary mid-range signed values round-trip correctly."""
        values = [
            0xDEADBEEFCAFEBABE,
            -0xDEADBEEFCAFEBABE,
            INT128_MAX // 2,
            INT128_MIN // 2,
            (1 << 64) - 1,
            1 << 64,
            -(1 << 64),
        ]
        for val in values:
            with self.subTest(val=val):
                self.assertEqual(
                    pylong_from_int128(pylong_as_int128(val)), val
                )

    def test_07_output_is_16_bytes(self) -> None:
        """pylong_as_int128 always returns exactly 16 bytes."""
        values = [0, 1, -1, INT128_MAX, INT128_MIN]
        for val in values:
            with self.subTest(val=val):
                result = pylong_as_int128(val)
                self.assertIsInstance(result, bytes)
                self.assertEqual(len(result), 16)


class TestAgainstStdlibOracle(unittest.TestCase):
    """Contract: pylong functions match Python stdlib int.to_bytes /
    int.from_bytes with matching byte order and signedness."""

    # ---- unsigned ----------------------------------------------------------

    def test_00_uint128_as_matches_oracle(self) -> None:
        """pylong_as_uint128 matches int.to_bytes(16, 'little', signed=False)."""
        values = [0, 1, 255, (1 << 64) - 1, UINT128_MAX // 7, UINT128_MAX]
        for val in values:
            with self.subTest(val=val):
                self.assertEqual(pylong_as_uint128(val), _uint128_oracle(val))

    def test_01_uint128_from_matches_oracle(self) -> None:
        """pylong_from_uint128 matches int.from_bytes(data, 'little', signed=False)."""
        data_values = [
            b'\x00' * 16,
            b'\x01' + b'\x00' * 15,
            b'\xff' * 16,  # UINT128_MAX
            b'\xff' * 8 + b'\x00' * 8,  # 2**64 - 1
            bytes(range(16)),  # arbitrary pattern
        ]
        for data in data_values:
            with self.subTest(data=data.hex()):
                self.assertEqual(
                    pylong_from_uint128(data), _from_uint128_oracle(data)
                )

    # ---- signed ------------------------------------------------------------

    def test_02_int128_as_matches_oracle(self) -> None:
        """pylong_as_int128 matches int.to_bytes(16, 'little', signed=True)."""
        values = [
            0, 1, -1, 127, -128,
            INT128_MAX,
            INT128_MIN,
            INT128_MAX // 3,
            INT128_MIN // 3,
        ]
        for val in values:
            with self.subTest(val=val):
                self.assertEqual(pylong_as_int128(val), _int128_oracle(val))

    def test_03_int128_from_matches_oracle(self) -> None:
        """pylong_from_int128 matches int.from_bytes(data, 'little', signed=True)."""
        data_values = [
            b'\x00' * 16,  # 0
            b'\x01' + b'\x00' * 15,  # 1
            b'\xff' * 16,  # -1
            b'\xff' * 15 + b'\x7f',  # INT128_MAX
            b'\x00' * 15 + b'\x80',  # INT128_MIN
            bytes(range(16)),  # arbitrary pattern
        ]
        for data in data_values:
            with self.subTest(data=data.hex()):
                self.assertEqual(
                    pylong_from_int128(data), _from_int128_oracle(data)
                )

    def test_04_signed_unsigned_cross_check(self) -> None:
        """Values in [0, INT128_MAX] give same bytes for signed and unsigned."""
        values = [0, 1, 127, 255, 0xFFFF, (1 << 64) - 1, INT128_MAX]
        for val in values:
            with self.subTest(val=val):
                self.assertEqual(
                    pylong_as_uint128(val), pylong_as_int128(val)
                )


class TestOverflowErrors(unittest.TestCase):
    """Contract: out-of-range values raise OverflowError."""

    def test_00_negative_uint128_raises(self) -> None:
        """Negative values cannot be represented as uint128_t."""
        with self.assertRaises(OverflowError):
            pylong_as_uint128(-1)

    def test_01_uint128_overflow_raises(self) -> None:
        """Values > UINT128_MAX raise OverflowError."""
        with self.assertRaises(OverflowError):
            pylong_as_uint128(UINT128_MAX + 1)

    def test_02_huge_uint128_raises(self) -> None:
        """Very large values raise OverflowError."""
        with self.assertRaises(OverflowError):
            pylong_as_uint128(2 ** 256)

    def test_03_int128_positive_overflow_raises(self) -> None:
        """Values > INT128_MAX raise OverflowError for int128_t."""
        with self.assertRaises(OverflowError):
            pylong_as_int128(INT128_MAX + 1)

    def test_04_int128_negative_overflow_raises(self) -> None:
        """Values < INT128_MIN raise OverflowError for int128_t."""
        with self.assertRaises(OverflowError):
            pylong_as_int128(INT128_MIN - 1)


class TestInvalidInputErrors(unittest.TestCase):
    """Contract: invalid inputs raise appropriate errors."""

    def test_00_from_uint128_wrong_size_raises(self) -> None:
        """Non-16-byte input raises ValueError."""
        with self.assertRaises(ValueError):
            pylong_from_uint128(b'\x00' * 8)

        with self.assertRaises(ValueError):
            pylong_from_uint128(b'\x00' * 17)

        with self.assertRaises(ValueError):
            pylong_from_uint128(b'')

    def test_01_from_int128_wrong_size_raises(self) -> None:
        """Non-16-byte input raises ValueError."""
        with self.assertRaises(ValueError):
            pylong_from_int128(b'\x00' * 8)

        with self.assertRaises(ValueError):
            pylong_from_int128(b'\x00' * 32)

    def test_02_as_uint128_non_int_raises(self) -> None:
        """Non-int input raises TypeError."""
        with self.assertRaises(TypeError):
            pylong_as_uint128("123")

        with self.assertRaises(TypeError):
            pylong_as_uint128(3.14)

    def test_03_as_int128_non_int_raises(self) -> None:
        """Non-int input raises TypeError."""
        with self.assertRaises(TypeError):
            pylong_as_int128(None)

        with self.assertRaises(TypeError):
            pylong_as_int128([1, 2, 3])

    def test_04_from_uint128_non_bytes_raises(self) -> None:
        """pylong_from_uint128 rejects non-bytes input."""
        with self.assertRaises(TypeError):
            pylong_from_uint128(bytearray(16))

        with self.assertRaises(TypeError):
            pylong_from_uint128([0] * 16)

    def test_05_from_int128_non_bytes_raises(self) -> None:
        """pylong_from_int128 rejects non-bytes input."""
        with self.assertRaises(TypeError):
            pylong_from_int128(memoryview(b'\x00' * 16))


class TestBoolIsInt(unittest.TestCase):
    """Contract: bool is a subclass of int, so bool values are accepted
    by pylong_as_*."""

    def test_00_bool_true_as_uint128(self) -> None:
        """True → 1 as uint128_t."""
        result = pylong_from_uint128(pylong_as_uint128(True))
        self.assertEqual(result, 1)

    def test_01_bool_false_as_int128(self) -> None:
        """False → 0 as int128_t."""
        result = pylong_from_int128(pylong_as_int128(False))
        self.assertEqual(result, 0)


if __name__ == '__main__':
    unittest.main()
