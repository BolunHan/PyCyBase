#ifndef PYLONG_COMP_H
#define PYLONG_COMP_H

#include <Python.h>
#include <stdint.h>
#include <string.h>

#if defined(__SIZEOF_INT128__)
typedef __int128_t     int128_t;
typedef __uint128_t    uint128_t;

static const uint128_t UINT128_MAX = (((uint128_t) 1) << 127) * 2 - 1;
static const int128_t  INT128_MAX = (int128_t) (UINT128_MAX >> 1);
static const int128_t  INT128_MIN = -((int128_t) (UINT128_MAX)) - 1;

static inline int      c_u128_cmp(const uint128_t v1, const uint128_t v2) {
    if (v1 < v2) return -1;
    if (v1 > v2) return 1;
    return 0;
}

static inline int c_i128_cmp(const int128_t v1, const int128_t v2) {
    if (v1 < v2) return -1;
    if (v1 > v2) return 1;
    return 0;
}
#else
/**
 * @brief MSVC has no native 128-bit integer -- emulate with a two-limb
 *        little-endian struct (memory layout identical to __uint128_t on
 *        x86-64, so 16-byte ID slots stay byte-compatible).
 *
 * The Cython boundary converts via int.to_bytes/from_bytes, so no 128-bit
 * arithmetic is required -- only 16-byte round-trips and ordered comparison.
 */
typedef struct {
    uint64_t lo;
    int64_t  hi;
} int128_t;
typedef struct {
    uint64_t lo;
    uint64_t hi;
} uint128_t;

static const uint128_t UINT128_MAX = {UINT64_MAX, UINT64_MAX};
static const int128_t  INT128_MAX = {UINT64_MAX, INT64_MAX};
static const int128_t  INT128_MIN = {0u, INT64_MIN};

static inline int      c_u128_cmp(const uint128_t v1, const uint128_t v2) {
    if (v1.hi != v2.hi) return v1.hi < v2.hi ? -1 : 1;
    if (v1.lo != v2.lo) return v1.lo < v2.lo ? -1 : 1;
    return 0;
}

static inline int c_i128_cmp(const int128_t v1, const int128_t v2) {
    if (v1.hi != v2.hi) return v1.hi < v2.hi ? -1 : 1;
    if (v1.lo != v2.lo) return v1.lo < v2.lo ? -1 : 1;
    return 0;
}
#endif

static inline void c_write_uint128(void* data, uint128_t value) {
    memcpy(data, &value, sizeof(uint128_t));
}

static inline uint128_t c_read_uint128(const void* data) {
    uint128_t value;
    memcpy(&value, data, sizeof(uint128_t));
    return value;
}

static inline void c_write_int128(void* data, int128_t value) {
    memcpy(data, &value, sizeof(int128_t));
}

static inline int128_t c_read_int128(const void* data) {
    int128_t value;
    memcpy(&value, data, sizeof(int128_t));
    return value;
}

static inline PyObject* PyLong_FromUInt128(uint128_t value) {
#if PY_VERSION_HEX >= 0x030D0000
    return PyLong_FromNativeBytes(&value, sizeof(value), Py_ASNATIVEBYTES_LITTLE_ENDIAN | Py_ASNATIVEBYTES_UNSIGNED_BUFFER);
#else
    return _PyLong_FromByteArray(
        (const unsigned char*) &value,
        sizeof(value),
        1, /* little_endian */
        0
    ); /* unsigned */
#endif
}

static inline PyObject* PyLong_FromInt128(int128_t value) {
#if PY_VERSION_HEX >= 0x030D0000
    return PyLong_FromNativeBytes(&value, sizeof(value), Py_ASNATIVEBYTES_LITTLE_ENDIAN);
#else
    return _PyLong_FromByteArray(
        (const unsigned char*) &value,
        sizeof(value),
        1, /* little_endian */
        1
    ); /* signed */
#endif
}

static inline Py_ssize_t PyLong_AsUInt128(PyObject* obj, uint128_t* value) {
#if PY_VERSION_HEX >= 0x030D0000
    return PyLong_AsNativeBytes(obj, value, sizeof(*value), Py_ASNATIVEBYTES_LITTLE_ENDIAN | Py_ASNATIVEBYTES_UNSIGNED_BUFFER);
#else
    if (!PyLong_Check(obj)) {
        PyErr_Format(PyExc_TypeError, "expected int, got %.200s", Py_TYPE(obj)->tp_name);
        return -1;
    }

    if (_PyLong_AsByteArray(
            (PyLongObject*) obj,
            (unsigned char*) value,
            sizeof(*value),
            1, /* little_endian */
            0
        ) < 0) {
        return -1;
    }

    return sizeof(*value);
#endif
}

static inline Py_ssize_t PyLong_AsInt128(PyObject* obj, int128_t* value) {
#if PY_VERSION_HEX >= 0x030D0000
    return PyLong_AsNativeBytes(obj, value, sizeof(*value), Py_ASNATIVEBYTES_LITTLE_ENDIAN);
#else
    if (!PyLong_Check(obj)) {
        PyErr_Format(PyExc_TypeError, "expected int, got %.200s", Py_TYPE(obj)->tp_name);
        return -1;
    }

    if (_PyLong_AsByteArray(
            (PyLongObject*) obj,
            (unsigned char*) value,
            sizeof(*value),
            1, /* little_endian */
            1
        ) < 0) {
        return -1;
    }

    return sizeof(*value);
#endif
}

#endif /* PYLONG_COMP_H */