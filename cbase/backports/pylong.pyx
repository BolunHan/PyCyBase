from cpython.bytes cimport PyBytes_FromStringAndSize

from cbase.int128 cimport c_read_uint128, c_write_uint128, c_read_int128, c_write_int128


globals()['_UINT128_MAX'] = _UINT128_MAX = (1 << 128) - 1
globals()['_INT128_MAX'] = _INT128_MAX = (1 << 127) - 1
globals()['_INT128_MIN'] = _INT128_MIN = -(1 << 127)


cpdef object pylong_from_uint128(bytes buf):
    if len(buf) != 16:
        raise ValueError(f"expected 16 bytes, got {len(buf)}")
    cdef uint128_t val = c_read_uint128(<const char*> buf)
    return <object> PyLong_FromUInt128(val)


cpdef object pylong_from_int128(bytes buf):
    if len(buf) != 16:
        raise ValueError(f"expected 16 bytes, got {len(buf)}")
    cdef int128_t val = c_read_int128(<const char*> buf)
    return <object> PyLong_FromInt128(val)


cpdef bytes pylong_as_uint128(object val):
    if not isinstance(val, int):
        raise TypeError(f"expected int, got {type(val).__name__}")

    if val < 0:
        raise OverflowError("can't convert negative int to uint128_t")
    if val > _UINT128_MAX:
        raise OverflowError("int too large for uint128_t")

    cdef uint128_t v
    cdef Py_ssize_t nbytes = PyLong_AsUInt128(<PyObject*> val, &v)

    if nbytes < 0:
        raise OverflowError("int out of range for uint128_t")
    if nbytes > <Py_ssize_t> sizeof(uint128_t):
        raise OverflowError("int too large for uint128_t")
    cdef bytes out = PyBytes_FromStringAndSize(NULL, 16)
    c_write_uint128(<char*> out, v)
    return out


cpdef bytes pylong_as_int128(object val):
    if not isinstance(val, int):
        raise TypeError(f"expected int, got {type(val).__name__}")

    if val < _INT128_MIN or val > _INT128_MAX:
        raise OverflowError("int out of range for int128_t")

    cdef int128_t v
    cdef Py_ssize_t nbytes = PyLong_AsInt128(<PyObject*> val, &v)
    if nbytes < 0:
        raise OverflowError("int out of range for int128_t")
    if nbytes > <Py_ssize_t> sizeof(int128_t):
        raise OverflowError("int too large for int128_t")
    cdef bytes out = PyBytes_FromStringAndSize(NULL, 16)
    c_write_int128(<char*> out, v)
    return out
