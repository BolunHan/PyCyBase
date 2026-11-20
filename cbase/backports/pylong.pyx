from cpython.bytes cimport PyBytes_FromStringAndSize

from cbase.int128 cimport c_read_uint128, c_write_uint128, c_read_int128, c_write_int128

cdef str UNSIGNED_SIZED_FORMAT = get_unsigned_sized_format()
cdef str SIGNED_SIZED_FORMAT = get_sized_format()

globals()['_UINT128_MAX'] = _UINT128_MAX = (1 << 128) - 1
globals()['_INT128_MAX'] = _INT128_MAX = (1 << 127) - 1
globals()['_INT128_MIN'] = _INT128_MIN = -(1 << 127)


cpdef object pylong_from_uint128(bytes buf):
    if len(buf) != 16:
        raise ValueError(f"expected 16 bytes, got {len(buf)}")
    cdef uint128_t val = c_read_uint128(<const char*> buf)
    return PyLong_FromUInt128(val)


cpdef object pylong_from_int128(bytes buf):
    if len(buf) != 16:
        raise ValueError(f"expected 16 bytes, got {len(buf)}")
    cdef int128_t val = c_read_int128(<const char*> buf)
    return PyLong_FromInt128(val)


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


cpdef str get_unsigned_sized_format():
    # Supported seamlessly by Python 3's struct / buffer engine
    cdef str native_format = "N"

    # 2. Explicit architectural type-matching safety check
    if sizeof(size_t) == 8:
        # Check if we are on a Windows 64-bit platform (LLP64 environment)
        # where long ("L") is only 4 bytes, requiring unsigned long long ("Q")
        if sizeof(long) == 4:
            return "Q"  # 8-byte unsigned integer (unsigned long long)
        else:
            return "L"  # 8-byte unsigned integer (unsigned long)
    else:
        return "I"      # 4-byte unsigned integer (unsigned int)


cpdef str get_sized_format():
    # Signed counterpart of get_unsigned_sized_format(): Py_ssize_t is the
    # signed type whose width tracks size_t, and Python's struct exposes it
    # natively as "n".
    cdef str native_format = "n"

    # 2. Explicit architectural type-matching safety check
    if sizeof(Py_ssize_t) == 8:
        # Check if we are on a Windows 64-bit platform (LLP64 environment)
        # where long ("l") is only 4 bytes, requiring signed long long ("q")
        if sizeof(long) == 4:
            return "q"  # 8-byte signed integer (signed long long)
        else:
            return "l"  # 8-byte signed integer (signed long)
    else:
        return "i"      # 4-byte signed integer (signed int)
