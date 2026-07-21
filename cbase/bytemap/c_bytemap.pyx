from time import perf_counter

from cpython.bytes cimport PyBytes_AsString, PyBytes_FromStringAndSize, PyBytes_GET_SIZE
from cpython.ref cimport Py_XINCREF
from cpython.unicode cimport PyUnicode_AsUTF8AndSize, PyUnicode_FromStringAndSize
from libc.math cimport NAN
from libc.stdlib cimport calloc, free
from libc.string cimport memset

from cbase.allocator_protocol.c_allocator_protocol cimport AP_DEFAULT_ALLOCATOR

cdef object NO_DEFAULT = object()
cdef bytes NO_DEFAULT_BYTES = b''


# ============================================================
#  _ByteMapBase — common base for all ByteMap variants
# ============================================================

cdef class _ByteMapBase:
    def __cinit__(self):
        self.header = NULL
        self.owner = False
        self.seq_id = 0

    def __dealloc__(self):
        if not self.owner:
            return
        if self.header:
            c_bytemap_ex_free(self.header)

    cdef void _init_header(self, size_t slot_capacity, size_t init_capacity):
        if slot_capacity == init_capacity == 0:
            return
        self.owner = True
        self.header = c_bytemap_ex_new(init_capacity, slot_capacity, AP_DEFAULT_ALLOCATOR)
        if self.header == NULL:
            raise MemoryError(f'Failed to allocate memory for <{self.__class__.__name__}>.')
        self.seq_id = c_bytemap_gen_seq_id(<void*> self)

    cdef void c_clear(self):
        c_bytemap_ex_clear(self.header)

    cdef void c_rehash(self, size_t new_capacity):
        cdef int ret_code = c_bytemap_ex_rehash(self.header, new_capacity, self.seq_id)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_OOM:
            raise MemoryError('Out of memory')
        else:
            raise RuntimeError(f'c_bytemap_ex_rehash failed with err code: {ret_code}')

    # === Shared Python Interfaces ===

    def __len__(self):
        return c_bytemap_ex_len(self.header)

    def clear(self):
        self.c_clear()

    property size:
        def __get__(self):
            if self.header:
                return self.header.size
            return 0

    property occupied:
        def __get__(self):
            if self.header:
                return self.header.occupied
            return 0

    property capacity:
        def __get__(self):
            if self.header:
                return self.header.capacity
            return 0

    property salt:
        def __get__(self):
            if self.header:
                return self.header.salt
            return 0

    property slot_capacity:
        def __get__(self):
            if self.header:
                return self.header.slot_capacity
            return 0


# ============================================================
#  ByteMapEx — str → bytes mapping
# ============================================================

cdef class ByteMapEx(_ByteMapBase):
    def __init__(self, size_t slot_capacity, size_t init_capacity=DEFAULT_BYTEMAP_CAPACITY):
        self._init_header(slot_capacity, init_capacity)

    @staticmethod
    cdef inline ByteMapEx c_from_header(bytemap* header, bint owner):
        cdef ByteMapEx instance = ByteMapEx.__new__(ByteMapEx)
        instance.header = header
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    @staticmethod
    cdef inline const char* c_key_to_string(str key, size_t* key_len):
        cdef Py_ssize_t out_len = 0
        cdef const char* out_ptr = PyUnicode_AsUTF8AndSize(key, &out_len)
        if key_len:
            key_len[0] = out_len
        return out_ptr

    @staticmethod
    cdef inline const char* c_value_to_string(bytes value, size_t* value_len):
        cdef Py_ssize_t out_len = PyBytes_GET_SIZE(value)
        cdef const char* out_ptr = <const char*> value
        if value_len:
            value_len[0] = out_len
        return out_ptr

    cdef bytes c_get(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef size_t out_len = 0
        cdef char* out = NULL
        cdef int ret_code = c_bytemap_ex_get_ptr(self.header, c_str, c_str_len, &out, &out_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return PyBytes_FromStringAndSize(out, out_len)
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'c_bytemap_ex_get_ptr failed with err code: {ret_code}')

    cdef void c_set(self, str key, bytes value):
        cdef size_t key_len = 0
        cdef const char* key_ptr = ByteMapEx.c_key_to_string(key, &key_len)
        cdef size_t value_len = 0
        cdef const char* value_ptr = ByteMapEx.c_value_to_string(value, &value_len)
        cdef int ret_code = c_bytemap_ex_set(self.header, key_ptr, key_len, value_ptr, value_len, self.seq_id, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_OOM:
            raise MemoryError('Out of memory')
        else:
            raise RuntimeError(f'c_bytemap_ex_set failed with err code: {ret_code}')

    cdef bytes c_pop(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef size_t out_len = 0
        cdef char* out = NULL
        cdef int ret_code = c_bytemap_ex_pop_ptr(self.header, c_str, c_str_len, self.seq_id, &out, &out_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return PyBytes_FromStringAndSize(out, out_len)
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'c_bytemap_ex_pop failed with err code: {ret_code}')

    cdef bint c_contains(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef int ret_code = c_bytemap_ex_contains(self.header, c_str, c_str_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        return False

    # === Python Interfaces ===

    def __contains__(self, str key):
        return self.c_contains(key)

    def __getitem__(self, str key):
        return self.c_get(key)

    def __setitem__(self, str key, bytes value):
        self.c_set(key, value)

    def __repr__(self):
        if self.header:
            return (f"<{self.__class__.__name__} {<uintptr_t> self.header:#0x}>("
                    f"size={self.header.size}, "
                    f"slot_capacity={self.header.slot_capacity}, "
                    f"occupied={self.header.occupied}, "
                    f"capacity={self.header.capacity})")
        return f"<{self.__class__.__name__} Unbound>"

    def __copy__(self):
        cdef bytemap* cloned = c_bytemap_ex_clone(self.header, AP_DEFAULT_ALLOCATOR)
        if cloned == NULL:
            raise MemoryError('Failed to clone ByteMapEx')
        return ByteMapEx.c_from_header(cloned, True)

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __iter__(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield PyUnicode_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def get(self, str key, bytes default=None, *):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef size_t out_len = 0
        cdef char* out = NULL
        cdef int ret_code = c_bytemap_ex_get_ptr(self.header, c_str, c_str_len, &out, &out_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return PyBytes_FromStringAndSize(out, out_len)
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return default
        else:
            raise RuntimeError(f'c_bytemap_ex_get_ptr failed with err code: {ret_code}')

    def set(self, str key, bytes value):
        return self.c_set(key, value)

    def pop(self, str key, bytes default=NO_DEFAULT_BYTES, *):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef size_t out_len = 0
        cdef char* out = NULL
        cdef int ret_code = c_bytemap_ex_pop_ptr(self.header, c_str, c_str_len, self.seq_id, &out, &out_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return PyBytes_FromStringAndSize(out, out_len)
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            if default is NO_DEFAULT_BYTES:
                raise KeyError(key)
            else:
                return default
        else:
            raise RuntimeError(f'c_bytemap_ex_pop failed with err code: {ret_code}')

    def contains(self, str key):
        return self.c_contains(key)

    def keys(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield PyUnicode_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def values(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield PyBytes_FromStringAndSize(entry.value, entry.value_length)
            entry = entry.next

    def items(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield (PyUnicode_FromStringAndSize(entry.key, entry.key_length),
                   PyBytes_FromStringAndSize(entry.value, entry.value_length))
            entry = entry.next

    def fork(self):
        return ByteMapEx.c_from_header(self.header, False)

    property as_dict:
        def __get__(self):
            cdef out = {}
            if not self.header:
                return out
            cdef bytemap_entry* entry = self.header.first
            cdef str key
            cdef bytes value
            while entry:
                key = PyUnicode_FromStringAndSize(entry.key, entry.key_length)
                value = PyBytes_FromStringAndSize(entry.value, entry.value_length)
                out[key] = value
                entry = entry.next
            return out


# ============================================================
#  ByteMapExDouble — str → double mapping
# ============================================================

cdef class ByteMapExDouble(_ByteMapBase):
    def __init__(self, size_t init_capacity=DEFAULT_BYTEMAP_CAPACITY):
        self._init_header(sizeof(double), init_capacity)

    cdef double c_get_double(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef double out
        cdef int ret_code = c_bytemap_ex_get_double(self.header, c_str, c_str_len, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'c_bytemap_ex_get_double failed with err code: {ret_code}')

    cdef void c_set_double(self, str key, double value):
        cdef size_t key_len = 0
        cdef const char* key_ptr = ByteMapEx.c_key_to_string(key, &key_len)
        cdef int ret_code = c_bytemap_ex_set_double(self.header, key_ptr, key_len, value, self.seq_id)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_OOM:
            raise MemoryError('Out of memory')
        else:
            raise RuntimeError(f'c_bytemap_ex_set failed with err code: {ret_code}')

    cdef double c_pop_double(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef double out
        cdef int ret_code = c_bytemap_ex_pop_double(self.header, c_str, c_str_len, self.seq_id, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'c_bytemap_ex_pop failed with err code: {ret_code}')

    # === Python Interfaces ===

    def __contains__(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef int ret_code = c_bytemap_ex_contains(self.header, c_str, c_str_len)
        return ret_code == bytemap_ret_code.BYTEMAP_OK

    def __getitem__(self, str key):
        return self.c_get_double(key)

    def __setitem__(self, str key, double value):
        self.c_set_double(key, value)

    def __repr__(self):
        if self.header:
            return (f"<{self.__class__.__name__} {<uintptr_t> self.header:#0x}>("
                    f"size={self.header.size}, "
                    f"slot_capacity={self.header.slot_capacity}, "
                    f"occupied={self.header.occupied}, "
                    f"capacity={self.header.capacity})")
        return f"<{self.__class__.__name__} Unbound>"

    def __copy__(self):
        cdef bytemap* cloned = c_bytemap_ex_clone(self.header, AP_DEFAULT_ALLOCATOR)
        if cloned == NULL:
            raise MemoryError('Failed to clone ByteMapExDouble')
        cdef ByteMapExDouble instance = ByteMapExDouble.__new__(ByteMapExDouble)
        instance.header = cloned
        instance.owner = True
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __iter__(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield PyUnicode_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def get(self, str key, double default=NAN, *):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef double out = default
        cdef int ret_code = c_bytemap_ex_get_double(self.header, c_str, c_str_len, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return default
        else:
            raise RuntimeError(f'c_bytemap_ex_get_double failed with err code: {ret_code}')

    def set(self, str key, double value):
        return self.c_set_double(key, value)

    def pop(self, str key, object default=NO_DEFAULT, *):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef double out = 0
        cdef int ret_code = c_bytemap_ex_pop_double(self.header, c_str, c_str_len, self.seq_id, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Uninitialized bytemap table')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise TypeError(f'Invalid key {key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            if default is NO_DEFAULT:
                raise KeyError(key)
            else:
                return <double> default
        else:
            raise RuntimeError(f'c_bytemap_ex_pop failed with err code: {ret_code}')

    def contains(self, str key):
        cdef size_t c_str_len = 0
        cdef const char* c_str = ByteMapEx.c_key_to_string(key, &c_str_len)
        cdef int ret_code = c_bytemap_ex_contains(self.header, c_str, c_str_len)
        return ret_code == bytemap_ret_code.BYTEMAP_OK

    def keys(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield PyUnicode_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def values(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield (<double*> entry.value)[0]
            entry = entry.next

    def items(self):
        cdef bytemap_entry* entry = self.header.first if self.header else NULL
        while entry:
            yield (PyUnicode_FromStringAndSize(entry.key, entry.key_length),
                   (<double*> entry.value)[0])
            entry = entry.next

    def fork(self):
        cdef ByteMapExDouble instance = ByteMapExDouble.__new__(ByteMapExDouble)
        instance.header = self.header
        instance.owner = False
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    property as_dict:
        def __get__(self):
            cdef out = {}
            if not self.header:
                return out
            cdef bytemap_entry* entry = self.header.first
            cdef str key
            cdef double value
            while entry:
                key = PyUnicode_FromStringAndSize(entry.key, entry.key_length)
                value = (<double*> entry.value)[0]
                out[key] = value
                entry = entry.next
            return out


# ============================================================
#  ByteMap — str/bytes → PyObject* mapping (void* variant)
# ============================================================

cdef class ByteMap(_ByteMapBase):
    def __init__(self, size_t init_capacity=DEFAULT_BYTEMAP_CAPACITY):
        self._init_header(sizeof(void*), init_capacity)

    @staticmethod
    cdef inline ByteMap c_from_header(bytemap* header, bint owner):
        cdef ByteMap instance = ByteMap.__new__(ByteMap)
        instance.header = header
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    # --- C-level API ---

    cdef inline void* c_get_ptr(self, const char* key):
        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key, 0, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError('Not found')
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void* c_get_bytes(self, bytes key_bytes):
        cdef size_t length = PyBytes_GET_SIZE(key_bytes)
        cdef const char* key = <const char*> key_bytes
        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key_bytes)
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void* c_get_str(self, str key_str):
        cdef Py_ssize_t length
        cdef const char* key = PyUnicode_AsUTF8AndSize(key_str, &length)
        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key_str)
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_set_ptr(self, const char* key, void* value):
        cdef int ret_code = c_bytemap_set(self.header, key, 0, value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_set_bytes(self, bytes key_bytes, void* value):
        cdef size_t length = PyBytes_GET_SIZE(key_bytes)
        cdef const char* key = <const char*> key_bytes
        cdef int ret_code = c_bytemap_set(self.header, key, length, value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_set_str(self, str key_str, void* value):
        cdef Py_ssize_t length
        cdef const char* key = PyUnicode_AsUTF8AndSize(key_str, &length)
        cdef int ret_code = c_bytemap_set(self.header, key, length, value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_pop_ptr(self, const char* key, void** out):
        cdef int ret_code = c_bytemap_pop(self.header, key, 0, out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError('Not found')
        else:
            raise RuntimeError(f'Failed to pop from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_pop_bytes(self, bytes key_bytes, void** out):
        cdef size_t length = PyBytes_GET_SIZE(key_bytes)
        cdef const char* key = <const char*> key_bytes
        cdef int ret_code = c_bytemap_pop(self.header, key, length, out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key_bytes)
        else:
            raise RuntimeError(f'Failed to pop from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline void c_pop_str(self, str key_str, void** out):
        cdef Py_ssize_t length
        cdef const char* key = PyUnicode_AsUTF8AndSize(key_str, &length)
        cdef int ret_code = c_bytemap_pop(self.header, key, length, out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key_str)
        else:
            raise RuntimeError(f'Failed to pop from {self.__class__.__name__}, err code: {ret_code}')

    cdef inline bint c_contains_ptr(self, const char* key):
        cdef int ret_code = c_bytemap_contains(self.header, key, 0)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return False
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        else:
            raise RuntimeError(f'Failed to check {self.__class__.__name__} contain, err code: {ret_code}')

    cdef inline bint c_contains_bytes(self, bytes key_bytes):
        cdef size_t length = PyBytes_GET_SIZE(key_bytes)
        cdef const char* key = <const char*> key_bytes
        cdef int ret_code = c_bytemap_contains(self.header, key, length)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return False
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        else:
            raise RuntimeError(f'Failed to check {self.__class__.__name__} contain, err code: {ret_code}')

    cdef inline bint c_contains_str(self, str key_str):
        cdef Py_ssize_t length
        cdef const char* key = PyUnicode_AsUTF8AndSize(key_str, &length)
        cdef int ret_code = c_bytemap_contains(self.header, key, length)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return False
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        else:
            raise RuntimeError(f'Failed to check {self.__class__.__name__} contain, err code: {ret_code}')

    # --- Python Interfaces ---

    def __contains__(self, object key):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef int ret_code = c_bytemap_contains(self.header, key_ptr, length)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return False
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        else:
            raise RuntimeError(f'Failed to check {self.__class__.__name__} contain, err code: {ret_code}')

    def __getitem__(self, object key):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key_ptr, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return <object> <PyObject*> out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    def __setitem__(self, object key, object value):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef int ret_code = c_bytemap_set(self.header, key_ptr, length, <void*> <PyObject*> value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>(size={self.header.size}, occupied={self.header.occupied}, capacity={self.header.capacity})"

    def __copy__(self):
        cdef bytemap* cloned = c_bytemap_clone(self.header, AP_DEFAULT_ALLOCATOR)
        if cloned == NULL:
            raise MemoryError('Failed to clone ByteMap')
        cdef ByteMap instance = ByteMap.__new__(ByteMap)
        instance.header = cloned
        instance.owner = True
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    def __deepcopy__(self, memo):
        return self.__copy__()

    cpdef uint64_t hash(self, object key):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')
        cdef uint64_t out
        cdef int ret_code = c_bytemap_hash(self.header, key_ptr, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return out
        raise RuntimeError(f'c_bytemap_hash failed with err_code: {ret_code}')

    def get(self, object key, object default=None):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key_ptr, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return <object> <PyObject*> out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return default
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    def get_addr(self, object key):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef void* out
        cdef int ret_code = c_bytemap_get(self.header, key_ptr, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return <uintptr_t> out
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            raise KeyError(key)
        else:
            raise RuntimeError(f'Failed to get from {self.__class__.__name__}, err code: {ret_code}')

    def set(self, object key, object value):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef int ret_code = c_bytemap_set(self.header, key_ptr, length, <void*> <PyObject*> value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    def set_addr(self, object key, uintptr_t value):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef int ret_code = c_bytemap_set(self.header, key_ptr, length, <void*> value, NULL)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    def pop(self, object key, object default=NO_DEFAULT, *):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef void* out
        cdef int ret_code = c_bytemap_pop(self.header, key_ptr, length, &out)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            if default is NO_DEFAULT:
                raise KeyError(key)
            else:
                return default
        else:
            raise RuntimeError(f'Failed to pop from {self.__class__.__name__}, err code: {ret_code}')

    def contains(self, key: str | bytes):
        cdef Py_ssize_t length
        cdef const char* key_ptr
        if isinstance(key, str):
            key_ptr = PyUnicode_AsUTF8AndSize(key, &length)
        elif isinstance(key, bytes):
            length = PyBytes_GET_SIZE(key)
            key_ptr = <const char*> key
        else:
            raise TypeError('Key must be str or bytes')

        cdef int ret_code = c_bytemap_contains(self.header, key_ptr, length)
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return True
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return False
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError('Invalid key')
        else:
            raise RuntimeError(f'Failed to check {self.__class__.__name__} contain, err code: {ret_code}')

    def bytes_keys(self):
        cdef bytemap_entry* entry = self.header.first
        while entry:
            yield PyBytes_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def str_keys(self):
        cdef bytemap_entry* entry = self.header.first
        while entry:
            yield PyUnicode_FromStringAndSize(entry.key, entry.key_length)
            entry = entry.next

    def values(self):
        cdef bytemap_entry* entry = self.header.first
        while entry:
            yield <uintptr_t> c_bytemap_entry_value(entry)
            entry = entry.next

    property capacity:
        def __get__(self):
            return self.header.capacity

        def __set__(self, size_t capacity):
            c_bytemap_rehash(self.header, capacity)

    property salt:
        def __get__(self):
            return self.header.salt

        def __set__(self, uint64_t salt):
            self.header.salt = salt


# ============================================================
#  _BoundByteMapBase — common base for all bound dict variants
# ============================================================

cdef class _BoundByteMapBase(dict):
    def __cinit__(self):
        self.header = NULL
        self.owner = False
        self.seq_id = 0
        self.callback_id = 0

    def __dealloc__(self):
        if self.callback_id:
            c_bytemap_ex_unregister_callback(self.header, self.callback_id)

        if not self.owner:
            return

        if self.header:
            c_bytemap_ex_free(self.header)

    cdef void _init_bound_header(self, size_t slot_capacity):
        self.header = c_bytemap_ex_new(DEFAULT_BYTEMAP_CAPACITY, slot_capacity, AP_DEFAULT_ALLOCATOR)
        self.seq_id = c_bytemap_gen_seq_id(<void*> self)
        cdef int ret_code = c_bytemap_ex_register_callback(
            self.header,
            self.c_sync,
            <void*> <PyObject*> self,
            &self.callback_id
        )

        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            c_bytemap_ex_free(self.header)
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')
        self.owner = True

    @staticmethod
    cdef void c_sync(bytemap_callback_event event,
                      const char* key, size_t key_len,
                      const char* value, size_t value_len,
                      uint64_t seq_id, void* user_data) noexcept:
        cdef PyObject* py_dict = <PyObject*> user_data
        cdef _BoundByteMapBase instance = <_BoundByteMapBase> py_dict
        cdef object py_key, py_value

        if event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_MODIFIED or event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_ADDED:
            if seq_id == instance.seq_id:
                return
            py_key = instance.c_deserialize_key(key, key_len)
            py_value = instance.c_deserialize_value(value, value_len)
            if PyDict_SetItem(py_dict, <PyObject*> py_key, <PyObject*> py_value) < 0:
                PyErr_Clear()
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_POPPED:
            if seq_id == instance.seq_id:
                return
            py_key = instance.c_deserialize_key(key, key_len)
            if PyDict_DelItem(py_dict, <PyObject*> py_key) < 0:
                PyErr_Clear()
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_CLEARED:
            PyDict_Clear(py_dict)
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_FREED:
            instance.header = NULL
            instance.callback_id = 0
            instance.owner = False
            PyDict_Clear(py_dict)

    cdef void c_bind(self, bytemap* header):
        if self.header:
            raise RuntimeError(f'{self.__class__.__name__} already bound')
        self.header = header
        self.owner = False

        cdef int ret_code = c_bytemap_ex_register_callback(
            header,
            self.c_sync,
            <void*> <PyObject*> self,
            &self.callback_id
        )
        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')

        dict.clear(self)
        cdef bytemap_entry* entry = header.first
        cdef object py_key, py_value
        while entry:
            py_key = self.c_deserialize_key(entry.key, entry.key_length)
            py_value = self.c_deserialize_value(entry.value, entry.value_length)
            if PyDict_SetItem(<PyObject*> self, <PyObject*> py_key, <PyObject*> py_value) < 0:
                PyErr_Clear()
            entry = entry.next

    cdef void c_rebind(self, bytemap* header):
        if self.callback_id:
            c_bytemap_ex_unregister_callback(self.header, self.callback_id)

        if self.owner:
            c_bytemap_ex_free(self.header)

        self.header = NULL
        self.c_bind(header)

    cdef const char* c_serialize_key(self, object obj, size_t* key_len):
        cdef const char* blob
        cdef Py_ssize_t blob_size
        if isinstance(obj, bytes):
            blob_size = PyBytes_GET_SIZE(obj)
            blob = <const char*> obj
        elif isinstance(obj, str):
            blob = PyUnicode_AsUTF8AndSize(obj, &blob_size)
        else:
            raise TypeError('Key must be str or bytes')

        if key_len:
            key_len[0] = blob_size
        return blob

    cdef object c_deserialize_key(self, const char* key, size_t key_len):
        return PyUnicode_FromStringAndSize(key, key_len)

    cdef const char* c_serialize_value(self, object obj, size_t* value_len):
        cdef Py_ssize_t out_len = PyBytes_GET_SIZE(obj)
        cdef const char* out_ptr = <const char*> obj
        if value_len:
            value_len[0] = out_len
        return out_ptr

    cdef object c_deserialize_value(self, const char* value, size_t value_len):
        return PyBytes_FromStringAndSize(value, value_len)

    cdef inline void c_sync_key(self, object py_key, const char* c_key, size_t c_key_len):
        cdef char* c_value = NULL
        cdef size_t c_value_len = 0
        cdef int ret_code = c_bytemap_ex_get_ptr(self.header, c_key, c_key_len, &c_value, &c_value_len)
        cdef object py_value
        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            py_value = self.c_deserialize_value(c_value, c_value_len)
            if PyDict_SetItem(<PyObject*> self, <PyObject*> py_key, <PyObject*> py_value) < 0:
                PyErr_Clear()
        else:
            if PyDict_DelItem(<PyObject*> self, <PyObject*> py_key) < 0:
                PyErr_Clear()

    cdef void c_set(self, object py_key, object py_value):
        cdef size_t c_key_len = 0
        cdef size_t c_value_len = 0
        cdef const char* c_key = self.c_serialize_key(py_key, &c_key_len)
        cdef const char* c_value = self.c_serialize_value(py_value, &c_value_len)

        PyDict_SetItem(<PyObject*> self, <PyObject*> py_key, <PyObject*> py_value)
        cdef int ret_code = c_bytemap_ex_set(self.header, c_key, c_key_len, c_value, c_value_len, self.seq_id, NULL)

        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        self.c_sync_key(py_key, c_key, c_key_len)

        if ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError(f'Invalid key {py_key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Mapping is full')
        else:
            raise RuntimeError(f'Failed to set to {self.__class__.__name__}, err code: {ret_code}')

    cdef object c_pop(self, object py_key, object default=NO_DEFAULT):
        cdef size_t c_key_len = 0
        cdef const char* c_key = self.c_serialize_key(py_key, &c_key_len)
        cdef PyObject* py_value = NULL

        if BP_PyDict_Pop(<PyObject*> self, <PyObject*> py_key, &py_value) < 0:
            PyErr_Clear()

        cdef char* c_value = NULL
        cdef size_t c_value_len = 0
        cdef int ret_code = c_bytemap_ex_pop_ptr(self.header, c_key, c_key_len, self.seq_id, &c_value, &c_value_len)

        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            if py_value:
                Py_XINCREF(py_value)
                return <object> py_value
            else:
                raise BufferError('c_pop succeeded but failed to pop from python dict cache. Likely caused by a buffer corruption.')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError(f'Invalid key {py_key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            if default is NO_DEFAULT:
                raise KeyError(py_key)
            else:
                return default
        else:
            raise RuntimeError(f'Failed to pop from {self.__class__.__name__}, err code: {ret_code}')

    cdef void c_update(self, dict payload):
        cdef object py_key, py_value
        for py_key, py_value in payload.items():
            self.c_set(py_key, py_value)

    cdef void c_clear(self):
        c_bytemap_ex_clear(self.header)

    # === Python Interfaces ===

    def __repr__(self):
        if self.header:
            return f'<{self.__class__.__name__} {<uintptr_t> self.header:#0x}>{dict.__repr__(self)}'
        return f'<{self.__class__.__name__} Unbound>{dict.__repr__(self)}'

    def __setitem__(self, object py_key, object py_value):
        self.c_set(py_key, py_value)

    def setdefault(self, object py_key, object default=NO_DEFAULT):
        if py_key in self:
            return self[py_key]
        if default is not NO_DEFAULT:
            self.c_set(py_key, default)
        else:
            raise KeyError(f'Invalid key {py_key}')
        return default

    def pop(self, object py_key, object default=NO_DEFAULT):
        return self.c_pop(py_key, default)

    def update(self, *args, **kwargs):
        cdef dict payload = dict(*args, **kwargs)
        self.c_update(payload)

    def clear(self):
        self.c_clear()

    def sync(self, object py_key):
        cdef size_t c_key_len = 0
        cdef const char* c_key = self.c_serialize_key(py_key, &c_key_len)
        self.c_sync_key(py_key, c_key, c_key_len)

    def fork(self):
        cdef object cls = self.__class__
        cdef object instance = cls.__new__(cls)

        cdef _BoundByteMapBase casted = <_BoundByteMapBase> instance
        casted.header = self.header
        casted.owner = False
        casted.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        cdef int ret_code = c_bytemap_ex_register_callback(
            self.header,
            _BoundByteMapBase.c_sync,
            <void*> <PyObject*> instance,
            &casted.callback_id
        )
        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')

        cdef bytemap_entry* entry = self.header.first
        cdef object py_key, py_value
        while entry:
            py_key = casted.c_deserialize_key(entry.key, entry.key_length)
            py_value = casted.c_deserialize_value(entry.value, entry.value_length)
            if PyDict_SetItem(<PyObject*> instance, <PyObject*> py_key, <PyObject*> py_value) < 0:
                PyErr_Clear()
            entry = entry.next

        return instance

    def rebind(self, object src):
        cdef bytemap* src_header
        if isinstance(src, _ByteMapBase):
            src_header = (<_ByteMapBase> src).header
        elif isinstance(src, _BoundByteMapBase):
            src_header = (<_BoundByteMapBase> src).header
        else:
            raise TypeError('src must be a ByteMap or BoundByteMap variant')
        self.c_rebind(src_header)


# ============================================================
#  BoundByteMapEx — synchronized dict (str → bytes)
# ============================================================

cdef class BoundByteMapEx(_BoundByteMapBase):
    def __init__(self, size_t slot_capacity=sizeof(void*), *args, **kwargs):
        self._init_bound_header(slot_capacity)
        super().__init__()
        cdef dict payload = dict(*args, **kwargs)
        if payload:
            self.c_update(payload)

    @staticmethod
    cdef BoundByteMapEx c_from_header(bytemap* header, bint owner=False):
        cdef BoundByteMapEx instance = BoundByteMapEx.__new__(BoundByteMapEx)
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        instance.c_bind(header)
        return instance


# ============================================================
#  BoundByteMapExDouble — synchronized dict (str → double)
# ============================================================

cdef class BoundByteMapExDouble(_BoundByteMapBase):
    def __init__(self, *args, **kwargs):
        self._init_bound_header(sizeof(double))
        super().__init__()
        cdef dict payload = dict(*args, **kwargs)
        if payload:
            self.c_update(payload)

    @staticmethod
    cdef BoundByteMapExDouble c_from_header(bytemap* header, bint owner=False):
        cdef BoundByteMapExDouble instance = BoundByteMapExDouble.__new__(BoundByteMapExDouble)
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        instance.c_bind(header)
        return instance

    cdef const char* c_serialize_value(self, object obj, size_t* value_len):
        self.ws = <double> float(obj)
        if value_len:
            value_len[0] = sizeof(double)
        return <const char*> &self.ws

    cdef object c_deserialize_value(self, const char* value, size_t value_len):
        cdef PyObject* py_value = PyFloat_FromDouble((<double*> value)[0])
        Py_XINCREF(py_value)
        return <object> py_value

    property ws:
        def __get__(self):
            return self.ws


# ============================================================
#  BoundByteMap — synchronized dict (str/bytes → PyObject*)
# ============================================================

cdef class BoundByteMap(_BoundByteMapBase):
    def __init__(self, *args, **kwargs):
        self._init_bound_header(sizeof(void*))
        super().__init__()
        cdef dict payload = dict(*args, **kwargs)
        if payload:
            self.c_update(payload)

    @staticmethod
    cdef BoundByteMap c_from_header(bytemap* header, bint owner=False):
        cdef BoundByteMap instance = BoundByteMap.__new__(BoundByteMap)
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        instance.c_bind(header)
        return instance

    cdef const char* c_serialize_value(self, object obj, size_t* value_len):
        self._ws_ptr = <void*> <PyObject*> obj
        if value_len:
            value_len[0] = sizeof(void*)
        return <const char*> &self._ws_ptr

    cdef object c_deserialize_value(self, const char* value, size_t value_len):
        cdef void** vp = <void**> value
        return <object> <PyObject*> vp[0]


# ============================================================
#  BoundByteSet — synchronized set backed by bytemap
# ============================================================

cdef class BoundByteSet(set):
    def __init__(self, *args, **kwargs):
        self.header = c_bytemap_new(DEFAULT_BYTEMAP_CAPACITY, AP_DEFAULT_ALLOCATOR)
        self.seq_id = c_bytemap_gen_seq_id(<void*> self)
        cdef int ret_code = c_bytemap_ex_register_callback(
            self.header,
            self.c_sync,
            <void*> <PyObject*> self,
            &self.callback_id
        )

        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            c_bytemap_free(self.header)
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')
        self.owner = True

        super().__init__()
        cdef set payload = set(*args, **kwargs)
        if payload:
            self.c_update(payload)

    def __dealloc__(self):
        if self.callback_id:
            c_bytemap_ex_unregister_callback(self.header, self.callback_id)

        if not self.owner:
            return

        if self.header:
            c_bytemap_free(self.header)

    @staticmethod
    cdef BoundByteSet c_from_header(bytemap* header, bint owner=False):
        cdef BoundByteSet instance = BoundByteSet.__new__(BoundByteSet)
        instance.owner = owner
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        instance.c_bind(header)
        return instance

    @staticmethod
    cdef void c_sync(bytemap_callback_event event,
                      const char* key, size_t key_len,
                      const char* value, size_t value_len,
                      uint64_t seq_id, void* user_data) noexcept:
        cdef BoundByteSet instance = <BoundByteSet> <PyObject*> user_data
        cdef object py_key

        if event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_MODIFIED or event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_ADDED:
            if seq_id == instance.seq_id:
                return
            py_key = instance.c_deserialize_key(key, key_len)
            set.add(instance, py_key)
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_POPPED:
            if seq_id == instance.seq_id:
                return
            py_key = instance.c_deserialize_key(key, key_len)
            set.discard(instance, py_key)
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_CLEARED:
            set.clear(instance)
        elif event == bytemap_callback_event.BYTEMAP_CALLBACK_EVENT_FREED:
            instance.header = NULL
            instance.callback_id = 0
            instance.owner = False
            set.clear(instance)

    cdef void c_bind(self, bytemap* header):
        if self.header:
            raise RuntimeError(f'{self.__class__.__name__} already bound')
        self.header = header
        self.owner = False

        cdef int ret_code = c_bytemap_ex_register_callback(
            header,
            self.c_sync,
            <void*> <PyObject*> self,
            &self.callback_id
        )
        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')

        set.clear(self)
        cdef bytemap_entry* entry = header.first
        cdef object py_key
        while entry:
            py_key = self.c_deserialize_key(entry.key, entry.key_length)
            set.add(self, py_key)
            entry = entry.next

    cdef void c_rebind(self, bytemap* header):
        if self.callback_id:
            c_bytemap_ex_unregister_callback(self.header, self.callback_id)

        if self.owner:
            c_bytemap_free(self.header)

        self.header = NULL
        self.c_bind(header)

    cdef const char* c_serialize_key(self, object obj, size_t* key_len):
        cdef const char* blob
        cdef Py_ssize_t blob_size
        if isinstance(obj, bytes):
            blob_size = PyBytes_GET_SIZE(obj)
            blob = <const char*> obj
        elif isinstance(obj, str):
            blob = PyUnicode_AsUTF8AndSize(obj, &blob_size)
        else:
            raise TypeError('Key must be str or bytes')

        if key_len:
            key_len[0] = blob_size
        return blob

    cdef object c_deserialize_key(self, const char* key, size_t key_len):
        return PyUnicode_FromStringAndSize(key, key_len)

    cdef inline void c_sync_key(self, object py_key, const char* c_key, size_t c_key_len, bint added):
        cdef int ret_code = c_bytemap_contains(self.header, c_key, c_key_len)
        if ret_code == bytemap_ret_code.BYTEMAP_OK and added:
            set.add(self, py_key)
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            set.discard(self, py_key)

    cdef void c_add(self, object py_key):
        cdef size_t c_key_len
        cdef const char* c_key = self.c_serialize_key(py_key, &c_key_len)
        cdef void* sentinel = <void*> 1

        set.add(self, py_key)

        cdef int ret_code = c_bytemap_ex_set(self.header, c_key, c_key_len, <const char*>&sentinel, sizeof(void*), self.seq_id, NULL)

        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return
        self.c_sync_key(py_key, c_key, c_key_len, ret_code == bytemap_ret_code.BYTEMAP_OK)

        if ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError(f'Invalid key {py_key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_FULL:
            raise MemoryError('Set is full')
        else:
            raise RuntimeError(f'Failed to add to {self.__class__.__name__}, err code: {ret_code}')

    cdef object c_discard(self, object py_key):
        cdef size_t c_key_len
        cdef const char* c_key = self.c_serialize_key(py_key, &c_key_len)
        cdef char* out = NULL
        cdef size_t out_len = 0

        cdef object py_removed = py_key if py_key in self else None
        set.discard(self, py_key)

        cdef int ret_code = c_bytemap_ex_pop_ptr(self.header, c_key, c_key_len, self.seq_id, &out, &out_len)

        if ret_code == bytemap_ret_code.BYTEMAP_OK:
            return py_removed
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_BUF:
            raise ValueError('Invalid args')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_INVALID_KEY:
            raise KeyError(f'Invalid key {py_key}')
        elif ret_code == bytemap_ret_code.BYTEMAP_ERR_NOT_FOUND:
            return None
        else:
            raise RuntimeError(f'Failed to discard from {self.__class__.__name__}, err code: {ret_code}')

    cdef void c_update(self, set payload):
        cdef object py_key
        for py_key in payload:
            self.c_add(py_key)

    cdef void c_clear(self):
        c_bytemap_clear(self.header)

    # === Python Interfaces ===

    def __repr__(self):
        if self.header:
            if len(self) > 5:
                return f'<{self.__class__.__name__} {<uintptr_t> self.header:#0x}>{{{", ".join(list(self)[:5])}...}}'
            return f'<{self.__class__.__name__} {<uintptr_t> self.header:#0x}>{{{", ".join(list(self))}}}'
        return f'<{self.__class__.__name__} Unbound>{{}}'

    def add(self, object py_key):
        self.c_add(py_key)

    def discard(self, object py_key):
        self.c_discard(py_key)

    def remove(self, object py_key):
        cdef object result = self.c_discard(py_key)
        if result is None:
            raise KeyError(py_key)

    def pop(self):
        if not self:
            raise KeyError('pop from an empty set')
        cdef object py_key = next(iter(self))
        self.c_discard(py_key)
        return py_key

    def update(self, *args):
        cdef set payload = set(*args) if args else set()
        self.c_update(payload)

    def clear(self):
        self.c_clear()

    def fork(self):
        cdef object cls = self.__class__
        cdef BoundByteSet instance = cls.__new__(cls)
        cdef int ret_code = c_bytemap_ex_register_callback(
            self.header,
            BoundByteSet.c_sync,
            <void*> <PyObject*> instance,
            &instance.callback_id
        )

        if ret_code != bytemap_ret_code.BYTEMAP_OK:
            raise RuntimeError(f'Failed to register callback for {self.__class__.__name__}, error code {ret_code}')

        cdef object py_key
        for py_key in self:
            set.add(instance, py_key)
        instance.header = self.header
        instance.owner = False
        instance.seq_id = c_bytemap_gen_seq_id(<void*> instance)
        return instance

    def rebind(self, object src):
        cdef bytemap* src_header
        if isinstance(src, _ByteMapBase):
            src_header = (<_ByteMapBase> src).header
        elif isinstance(src, _BoundByteMapBase):
            src_header = (<_BoundByteMapBase> src).header
        elif isinstance(src, BoundByteSet):
            src_header = (<BoundByteSet> src).header
        else:
            raise TypeError('src must be a ByteMap, BoundByteMap or BoundByteSet variant')
        self.c_rebind(src_header)


# ============================================================
#  ByteMapPerformanceTestToolkit
# ============================================================

cdef class ByteMapPerformanceTestToolkit:
    @staticmethod
    def gen_seq_id(uintptr_t addr):
        """Generate a seq_id from an address using c_bytemap_gen_seq_id.

        Public for testing multiprocessing seq_id uniqueness across processes.
        """
        return c_bytemap_gen_seq_id(<void*> addr)

    def __cinit__(self, size_t n_iters=1_000, size_t n_payloads=1_000):
        self.n_iters = n_iters
        self.n_payloads = n_payloads
        self.py_keys = []
        self.py_payloads = []
        self.py_map = {}
        self.c_map = c_bytemap_new(0, AP_DEFAULT_ALLOCATOR)
        if self.c_map == NULL:
            raise MemoryError(f'Failed to allocate memory for <{self.__class__.__name__}>.')

        if n_payloads == 0:
            self.payloads = NULL
            self.keys = NULL
            return

        self.payloads = <PyObject**> calloc(n_payloads, sizeof(PyObject*))
        self.keys = <const char**> calloc(n_payloads, sizeof(char*))
        if self.payloads == NULL or self.keys == NULL:
            if self.payloads != NULL:
                free(self.payloads)
                self.payloads = NULL
            if self.keys != NULL:
                free(self.keys)
                self.keys = NULL
            c_bytemap_free(self.c_map)
            self.c_map = NULL
            raise MemoryError(f'Failed to allocate benchmark buffers for <{self.__class__.__name__}>.')

        self.c_gen_keys()
        self.c_gen_payloads()

    def __dealloc__(self):
        if self.payloads != NULL:
            free(self.payloads)
            self.payloads = NULL
        if self.keys != NULL:
            free(self.keys)
            self.keys = NULL
        if self.c_map != NULL:
            c_bytemap_free(self.c_map)
            self.c_map = NULL

    cdef inline void c_gen_keys(self):
        cdef size_t i
        cdef bytes key_obj
        if self.keys != NULL and self.n_payloads > 0:
            memset(<void*> self.keys, 0, self.n_payloads * sizeof(char*))
        self.py_keys = []
        for i in range(self.n_payloads):
            key_obj = f'bench_key_{i:08d}'.encode('ascii')
            self.py_keys.append(key_obj)
            self.keys[i] = PyBytes_AsString(key_obj)

    cdef inline void c_gen_payloads(self):
        cdef size_t i
        cdef object payload
        if self.payloads != NULL and self.n_payloads > 0:
            memset(<void*> self.payloads, 0, self.n_payloads * sizeof(PyObject*))
        self.py_payloads = []
        for i in range(self.n_payloads):
            payload = object()
            self.py_payloads.append(payload)
            self.payloads[i] = <PyObject*> payload

    cdef inline void c_prepare_py_map(self):
        cdef size_t i
        PyDict_Clear(<PyObject*> self.py_map)
        for i in range(self.n_payloads):
            if PyDict_SetItemString(<PyObject*> self.py_map, self.keys[i], <PyObject*> self.payloads[i]) != 0:
                raise RuntimeError('PyDict_SetItemString failed during benchmark preparation')

    cdef inline void c_prepare_c_map(self):
        cdef size_t i
        c_bytemap_clear(self.c_map)
        for i in range(self.n_payloads):
            if c_bytemap_set(self.c_map, self.keys[i], 0, <void*> self.payloads[i], NULL) != bytemap_ret_code.BYTEMAP_OK:
                raise RuntimeError('c_bytemap_set failed during benchmark preparation')

    cpdef double c_map_set_routine(self):
        cdef size_t iter_idx
        cdef size_t payload_idx
        cdef double elapsed = 0.0
        cdef double start_ts

        for iter_idx in range(self.n_iters):
            c_bytemap_clear(self.c_map)
            start_ts = perf_counter()
            for payload_idx in range(self.n_payloads):
                if c_bytemap_set(self.c_map, self.keys[payload_idx], 0, <void*> self.payloads[payload_idx], NULL) != bytemap_ret_code.BYTEMAP_OK:
                    raise RuntimeError('c_bytemap_set failed during benchmark')
            elapsed += perf_counter() - start_ts

        self.c_checksum = 0
        for payload_idx in range(self.n_payloads):
            self.c_checksum += <uintptr_t> self.payloads[payload_idx]
        return elapsed

    cpdef double py_map_set_routine(self):
        cdef size_t iter_idx
        cdef size_t payload_idx
        cdef double elapsed = 0.0
        cdef double start_ts

        for iter_idx in range(self.n_iters):
            PyDict_Clear(<PyObject*> self.py_map)
            start_ts = perf_counter()
            for payload_idx in range(self.n_payloads):
                if PyDict_SetItemString(<PyObject*> self.py_map, self.keys[payload_idx], <PyObject*> self.payloads[payload_idx]) != 0:
                    raise RuntimeError('PyDict_SetItemString failed during benchmark')
            elapsed += perf_counter() - start_ts

        self.py_checksum = 0
        for payload_idx in range(self.n_payloads):
            self.py_checksum += <uintptr_t> self.payloads[payload_idx]
        return elapsed

    cpdef double c_map_get_routine(self):
        cdef size_t iter_idx
        cdef size_t payload_idx
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef void* out = NULL
        cdef uintptr_t checksum = 0

        self.c_prepare_c_map()
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for payload_idx in range(self.n_payloads):
                out = NULL
                if c_bytemap_get(self.c_map, self.keys[payload_idx], 0, &out) != bytemap_ret_code.BYTEMAP_OK:
                    raise RuntimeError('c_bytemap_get failed during benchmark')
                checksum += <uintptr_t> out
            elapsed += perf_counter() - start_ts

        self.c_checksum = checksum
        return elapsed

    cpdef double py_map_get_routine(self):
        cdef size_t iter_idx
        cdef size_t payload_idx
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef PyObject* out
        cdef uintptr_t checksum = 0

        self.c_prepare_py_map()
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for payload_idx in range(self.n_payloads):
                out = PyDict_GetItemString(<PyObject*> self.py_map, self.keys[payload_idx])
                if out == NULL:
                    raise RuntimeError('PyDict_GetItemString failed during benchmark')
                checksum += <uintptr_t> out
            elapsed += perf_counter() - start_ts

        self.py_checksum = checksum
        return elapsed

    cpdef dict run_test(self):
        cdef double c_set = self.c_map_set_routine()
        cdef double py_set = self.py_map_set_routine()
        cdef double c_get = self.c_map_get_routine()
        cdef double py_get = self.py_map_get_routine()

        return {
            'n_iters': self.n_iters,
            'n_payloads': self.n_payloads,
            'c_set': c_set,
            'py_set': py_set,
            'c_get': c_get,
            'py_get': py_get,
            'c_checksum': self.c_checksum,
            'py_checksum': self.py_checksum,
        }
