#ifndef PY_BACKPORTS_LONG_H
#define PY_BACKPORTS_LONG_H

#include <Python.h>
#include <cbase/int128.h>

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

#endif  // PY_BACKPORTS_LONG_H
