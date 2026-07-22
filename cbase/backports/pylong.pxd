from cpython.object cimport PyObject


cdef extern from "cbase/backports/pylong.h":
    ctypedef unsigned long long uint128_t
    ctypedef long long int128_t

    const int128_t INT128_MIN
    const int128_t INT128_MAX
    const uint128_t UINT128_MAX

    # Read/write 128-bit values from/to byte buffers
    uint128_t c_read_uint128(const void* data)
    void      c_write_uint128(void* data, uint128_t value)
    int128_t  c_read_int128(const void* data)
    void      c_write_int128(void* data, int128_t value)

    # Python int ↔ 128-bit conversion
    PyObject*  PyLong_FromUInt128(uint128_t value)
    PyObject*  PyLong_FromInt128(int128_t value)
    Py_ssize_t PyLong_AsUInt128(PyObject* obj, uint128_t* value)
    Py_ssize_t PyLong_AsInt128(PyObject* obj, int128_t* value)

    # 128-bit comparison
    int c_u128_cmp(uint128_t v1, uint128_t v2)
    int c_i128_cmp(int128_t v1, int128_t v2)


cdef object _UINT128_MAX
cdef object _INT128_MAX
cdef object _INT128_MIN

cpdef object pylong_from_uint128(bytes buf)

cpdef object pylong_from_int128(bytes buf)

cpdef bytes pylong_as_uint128(object val)

cpdef bytes pylong_as_int128(object val)
