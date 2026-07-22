from cpython.object cimport PyObject

from cbase.int128 cimport uint128_t, int128_t


cdef extern from "cbase/backports/pylong.h":
    PyObject*  PyLong_FromUInt128(uint128_t value)
    PyObject*  PyLong_FromInt128(int128_t value)
    Py_ssize_t PyLong_AsUInt128(PyObject* obj, uint128_t* value)
    Py_ssize_t PyLong_AsInt128(PyObject* obj, int128_t* value)


cdef object _UINT128_MAX
cdef object _INT128_MAX
cdef object _INT128_MIN

cpdef object pylong_from_uint128(bytes buf)

cpdef object pylong_from_int128(bytes buf)

cpdef bytes pylong_as_uint128(object val)

cpdef bytes pylong_as_int128(object val)
