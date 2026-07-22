from cpython.object cimport PyObject
from libc.stdint cimport uint64_t, uintptr_t
from libcpp cimport bool as c_bool

from cbase.allocator_protocol.c_allocator_protocol cimport allocator_protocol


cdef extern from "cbase/bytemap/xxh3.h":
    uint64_t XXH3_64bits(const void* input, size_t length) noexcept nogil
    uint64_t XXH3_64bits_withSeed(const void* input, size_t length, uint64_t seed) noexcept nogil


cdef extern from "Python.h":
    PyObject* PyDict_GetItem(PyObject* p, PyObject* key)
    int PyDict_SetItem(PyObject* p, PyObject* key, PyObject* val)
    int PyDict_DelItem(PyObject* p, PyObject* key)
    void PyDict_Clear(PyObject* p)
    int PyDict_SetItemString(PyObject* p, const char* key, PyObject* val)
    PyObject* PyDict_GetItemString(PyObject* p, const char* key)
    PyObject* PyFloat_FromDouble(double v)
    void PyErr_Clear()


cdef extern from "cbase/bytemap/c_bytemap.h":
    const size_t MIN_BYTEMAP_CAPACITY
    const size_t DEFAULT_BYTEMAP_CAPACITY
    const size_t BYTEMAP_GROWTH_FACTOR
    const size_t MAX_BYTEMAP_CAPACITY
    const uint64_t BYTEMAP_SALT_MAGIC

    ctypedef struct bytemap_entry:
        uint64_t hash
        size_t key_length
        const char* key
        size_t value_length
        c_bool occupied
        c_bool removed
        bytemap_entry* prev
        bytemap_entry* next
        char value[]

    ctypedef bytemap_entry bytemap_entry_ex

    ctypedef enum bytemap_callback_event:
        BYTEMAP_CALLBACK_EVENT_MODIFIED
        BYTEMAP_CALLBACK_EVENT_ADDED
        BYTEMAP_CALLBACK_EVENT_POPPED
        BYTEMAP_CALLBACK_EVENT_CLEARED
        BYTEMAP_CALLBACK_EVENT_REHASH
        BYTEMAP_CALLBACK_EVENT_FREED

    ctypedef void (*bytemap_callback_func)(bytemap_callback_event event, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, void* user_data) noexcept

    ctypedef bytemap_callback_func bytemap_ex_callback_func

    ctypedef struct bytemap_callback_ctx:
        bytemap_callback_func fn
        void* user_data
        uintptr_t id
        bytemap_callback_ctx* next

    ctypedef bytemap_callback_ctx bytemap_ex_callback_ctx

    ctypedef struct bytemap:
        bytemap_entry* table
        bytemap_entry* first
        bytemap_entry* last
        bytemap_callback_ctx* callbacks
        size_t capacity
        size_t size
        size_t occupied
        uint64_t salt
        size_t slot_capacity
        size_t entry_size
        void* table_end

    ctypedef bytemap bytemap_ex

    ctypedef enum bytemap_ret_code:
        BYTEMAP_OK
        BYTEMAP_ERR_INVALID_BUF
        BYTEMAP_ERR_INVALID_KEY
        BYTEMAP_ERR_INVALID_VALUE
        BYTEMAP_ERR_NOT_FOUND
        BYTEMAP_ERR_FULL
        BYTEMAP_ERR_EMPTY
        BYTEMAP_ERR_OOM

    int c_bytemap_hash(const bytemap* bmap, const char* key, size_t key_len, uint64_t* out) noexcept nogil
    const char* c_bytemap_clone_key(const bytemap* bmap, const char* key, size_t key_len) noexcept nogil
    void c_bytemap_free_key(const bytemap* bmap, char* key) noexcept nogil
    uint64_t c_bytemap_gen_seq_id(const void* ptr) noexcept nogil
    bytemap_entry* c_bytemap_entry_at(const bytemap* bmap, size_t idx) noexcept nogil
    bytemap_entry* c_bytemap_entry_next(const bytemap* bmap, bytemap_entry* entry) noexcept nogil
    bytemap_entry* c_bytemap_entry_first(const bytemap* bmap) noexcept nogil
    void c_bytemap_invoke_callbacks(bytemap_callback_event event, const bytemap* bmap, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id) noexcept nogil

    int c_bytemap_ex_init(bytemap* bmap, size_t capacity, size_t slot_capacity, allocator_protocol* allocator) noexcept nogil
    void c_bytemap_ex_dealloc(bytemap* bmap) noexcept nogil
    bytemap* c_bytemap_ex_new(size_t capacity, size_t slot_capacity, allocator_protocol* allocator) noexcept nogil
    void c_bytemap_ex_clear(bytemap* bmap) noexcept nogil
    void c_bytemap_ex_free(bytemap* bmap) noexcept nogil
    int c_bytemap_ex_register_callback(bytemap* bmap, bytemap_callback_func callback, void* user_data, uintptr_t* out_id) noexcept nogil
    int c_bytemap_ex_unregister_callback(bytemap* bmap, uintptr_t callback_id) noexcept nogil
    int c_bytemap_ex_get(const bytemap* bmap, const char* key, size_t key_len, char* out, size_t* out_len) noexcept nogil
    int c_bytemap_ex_get_ptr(const bytemap* bmap, const char* key, size_t key_len, char** out, size_t* out_len) noexcept nogil
    int c_bytemap_ex_contains(const bytemap* bmap, const char* key, size_t key_len) noexcept nogil
    int c_bytemap_ex_rehash(bytemap* bmap, size_t new_capacity, uint64_t seq_id) noexcept nogil
    int c_bytemap_ex_set(bytemap* bmap, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, bytemap_entry** out) noexcept nogil
    int c_bytemap_ex_pop(bytemap* bmap, const char* key, size_t key_len, uint64_t seq_id, char* out, size_t* out_len) noexcept nogil
    int c_bytemap_ex_pop_ptr(bytemap* bmap, const char* key, size_t key_len, uint64_t seq_id, char** out, size_t* out_len) noexcept nogil
    size_t c_bytemap_ex_len(const bytemap* bmap) noexcept nogil
    bytemap* c_bytemap_ex_clone(const bytemap* src, allocator_protocol* allocator) noexcept nogil

    int c_bytemap_ex_set_double(bytemap* bmap, const char* key, size_t key_len, double value, uint64_t seq_id) noexcept nogil
    int c_bytemap_ex_get_double(const bytemap* bmap, const char* key, size_t key_len, double* out) noexcept nogil
    int c_bytemap_ex_pop_double(bytemap* bmap, const char* key, size_t key_len, uint64_t seq_id, double* out) noexcept nogil

    bytemap* c_bytemap_new(size_t capacity, allocator_protocol* allocator) noexcept nogil
    void c_bytemap_clear(bytemap* bmap) noexcept nogil
    void c_bytemap_free(bytemap* bmap) noexcept nogil
    int c_bytemap_register_callback(bytemap* bmap, bytemap_callback_func callback, void* user_data, uintptr_t* out_id) noexcept nogil
    int c_bytemap_unregister_callback(bytemap* bmap, uintptr_t callback_id) noexcept nogil
    int c_bytemap_get(const bytemap* bmap, const char* key, size_t key_len, void** out) noexcept nogil
    int c_bytemap_contains(const bytemap* bmap, const char* key, size_t key_len) noexcept nogil
    int c_bytemap_rehash(bytemap* bmap, size_t new_capacity) noexcept nogil
    int c_bytemap_set(bytemap* bmap, const char* key, size_t key_len, void* value, bytemap_entry** out) noexcept nogil
    int c_bytemap_pop(bytemap* bmap, const char* key, size_t key_len, void** out) noexcept nogil
    size_t c_bytemap_len(const bytemap* bmap) noexcept nogil
    bytemap* c_bytemap_clone(const bytemap* src, allocator_protocol* allocator) noexcept nogil
    bytemap_entry* c_bytemap_first(const bytemap* bmap) noexcept nogil
    bytemap_entry* c_bytemap_last(const bytemap* bmap) noexcept nogil
    bytemap_entry* c_bytemap_next(const bytemap_entry* entry) noexcept nogil
    bytemap_entry* c_bytemap_prev(const bytemap_entry* entry) noexcept nogil
    void* c_bytemap_entry_value(const bytemap_entry* entry) noexcept nogil
    void* c_bytemap_entry_value_as_ptr(const bytemap_entry* entry) noexcept nogil
    uintptr_t c_bytemap_entry_value_as_uintptr(const bytemap_entry* entry) noexcept nogil
    double c_bytemap_entry_value_as_double(const bytemap_entry* entry) noexcept nogil

    void c_bytemap_entry_value_from_ptr(bytemap_entry* entry, const void* ptr) noexcept nogil
    void c_bytemap_entry_value_from_uintptr(bytemap_entry* entry, uintptr_t val) noexcept nogil
    void c_bytemap_entry_value_from_double(bytemap_entry* entry, double val) noexcept nogil


cdef object NO_DEFAULT


# ============================================================
#  _ByteMapBase — common base for all ByteMap variants
# ============================================================

cdef class _ByteMapBase:
    cdef bytemap* header
    cdef bint owner
    cdef uint64_t seq_id

    cdef void _init_header(self, size_t slot_capacity, size_t init_capacity)

    cdef void c_clear(self)

    cdef void c_rehash(self, size_t new_capacity)


# ============================================================
#  ByteMapEx — str → bytes mapping
# ============================================================

cdef class ByteMapEx(_ByteMapBase):
    @staticmethod
    cdef inline ByteMapEx c_from_header(bytemap* header, bint owner)

    @staticmethod
    cdef inline const char* c_key_to_string(str key, size_t* key_len)

    @staticmethod
    cdef inline const char* c_value_to_string(bytes value, size_t* value_len)

    cdef bytes c_get(self, str key)

    cdef void c_set(self, str key, bytes value)

    cdef bytes c_pop(self, str key)

    cdef bint c_contains(self, str key)


# ============================================================
#  ByteMapExDouble — str → double mapping
# ============================================================

cdef class ByteMapExDouble(_ByteMapBase):
    cdef double c_get_double(self, str key)

    cdef void c_set_double(self, str key, double value)

    cdef double c_pop_double(self, str key)


# ============================================================
#  ByteMap — str/bytes → PyObject* mapping (void* variant)
# ============================================================

cdef class ByteMap(_ByteMapBase):
    @staticmethod
    cdef inline ByteMap c_from_header(bytemap* header, bint owner)

    cdef inline void* c_get_ptr(self, const char* key_ptr)

    cdef inline void* c_get_bytes(self, bytes key_bytes)

    cdef inline void* c_get_str(self, str key_str)

    cdef inline void c_set_ptr(self, const char* key_ptr, void* value)

    cdef inline void c_set_bytes(self, bytes key_bytes, void* value)

    cdef inline void c_set_str(self, str key_str, void* value)

    cdef inline void c_pop_ptr(self, const char* key_ptr, void** out)

    cdef inline void c_pop_bytes(self, bytes key_bytes, void** out)

    cdef inline void c_pop_str(self, str key_str, void** out)

    cdef inline bint c_contains_ptr(self, const char* key_ptr)

    cdef inline bint c_contains_bytes(self, bytes key_bytes)

    cdef inline bint c_contains_str(self, str key_str)

    cpdef uint64_t hash(self, object key)


# ============================================================
#  _BoundByteMapBase — common base for all bound dict variants
# ============================================================

cdef class _BoundByteMapBase(dict):
    cdef bytemap* header
    cdef bint owner
    cdef uint64_t seq_id
    cdef uintptr_t callback_id

    @staticmethod
    cdef void c_sync(bytemap_callback_event event, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, void* user_data) noexcept

    cdef void _init_bound_header(self, size_t slot_capacity)

    cdef void c_bind(self, bytemap* header)

    cdef void c_rebind(self, bytemap* header)

    cdef const char* c_serialize_key(self, object obj, size_t* key_len)

    cdef object c_deserialize_key(self, const char* key, size_t key_len)

    cdef const char* c_serialize_value(self, object obj, size_t* value_len)

    cdef object c_deserialize_value(self, const char* value, size_t value_len)

    cdef void c_sync_key(self, object py_key, const char* c_key, size_t c_key_len)

    cdef void c_set(self, object py_key, object py_value)

    cdef object c_pop(self, object py_key, object default=?)

    cdef void c_update(self, dict payload)

    cdef void c_clear(self)


# ============================================================
#  BoundByteMapEx — synchronized dict (str → bytes)
# ============================================================

cdef class BoundByteMapEx(_BoundByteMapBase):
    @staticmethod
    cdef BoundByteMapEx c_from_header(bytemap* header, bint owner=?)


# ============================================================
#  BoundByteMapExDouble — synchronized dict (str → double)
# ============================================================

cdef class BoundByteMapExDouble(_BoundByteMapBase):
    cdef double ws

    @staticmethod
    cdef BoundByteMapExDouble c_from_header(bytemap* header, bint owner=?)


# ============================================================
#  BoundByteMap — synchronized dict (str/bytes → PyObject*)
# ============================================================

cdef class BoundByteMap(_BoundByteMapBase):
    cdef void* _ws_ptr

    @staticmethod
    cdef BoundByteMap c_from_header(bytemap* header, bint owner=?)


# ============================================================
#  BoundByteSet — synchronized set backed by bytemap
# ============================================================

cdef class BoundByteSet(set):
    cdef bytemap* header
    cdef bint owner
    cdef uint64_t seq_id
    cdef uintptr_t callback_id

    @staticmethod
    cdef BoundByteSet c_from_header(bytemap* header, bint owner=?)

    @staticmethod
    cdef void c_sync(bytemap_callback_event event, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, void* user_data) noexcept

    cdef void c_bind(self, bytemap* header)

    cdef void c_rebind(self, bytemap* header)

    cdef const char* c_serialize_key(self, object obj, size_t* key_len)

    cdef object c_deserialize_key(self, const char* key, size_t key_len)

    cdef inline void c_sync_key(self, object py_key, const char* c_key, size_t c_key_len, bint added)

    cdef void c_add(self, object py_key)

    cdef object c_discard(self, object py_key)

    cdef void c_update(self, set payload)

    cdef void c_clear(self)


# ============================================================
#  ByteMapPerformanceTestToolkit
# ============================================================

cdef class ByteMapPerformanceTestToolkit:
    cdef PyObject** payloads
    cdef const char** keys
    cdef readonly size_t n_iters
    cdef readonly size_t n_payloads
    cdef readonly list py_keys
    cdef readonly list py_payloads
    cdef bytemap* c_map
    cdef dict py_map
    cdef uintptr_t c_checksum
    cdef uintptr_t py_checksum

    cdef inline void c_gen_keys(self)

    cdef inline void c_gen_payloads(self)

    cdef inline void c_prepare_py_map(self)

    cdef inline void c_prepare_c_map(self)

    cpdef double c_map_set_routine(self)

    cpdef double py_map_set_routine(self)

    cpdef double c_map_get_routine(self)

    cpdef double py_map_get_routine(self)

    cpdef dict run_test(self)
