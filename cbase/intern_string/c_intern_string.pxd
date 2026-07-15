from libc.stdint cimport uint64_t

from cbase.allocator_protocol.c_allocator_protocol cimport allocator_protocol


cdef extern from "cbase/intern_string/c_intern_string.h":
    # === Constants ===
    size_t ISTR_INITIAL_CAPACITY

    ctypedef struct pthread_mutex_t:
        pass

    # === Structs ===
    ctypedef struct istr_entry:
        const char* key
        size_t key_length
        uint64_t hash
        istr_entry* next

    ctypedef struct istr_map:
        pass

    int pthread_mutex_init(pthread_mutex_t* mutex, void* attr) noexcept nogil
    int pthread_mutex_lock(pthread_mutex_t* mutex) noexcept nogil
    int pthread_mutex_unlock(pthread_mutex_t* mutex) noexcept nogil
    int pthread_mutex_destroy(pthread_mutex_t* mutex) noexcept nogil

    # === Unified accessors ===
    size_t istr_map_size(const istr_map* map) noexcept nogil
    istr_entry* istr_map_first(const istr_map* map) noexcept nogil
    size_t istr_map_capacity(const istr_map* map) noexcept nogil

    # === Hash ===
    uint64_t fnv1a_hash(const char* key, size_t key_length)

    # === Map lifecycle ===
    istr_map* c_istr_map_new(size_t capacity, allocator_protocol* allocator)
    void c_istr_map_free(istr_map* imap)

    # === Extend ===
    int c_istr_map_extend(istr_map* imap, size_t new_capacity)
    int c_istr_map_extend_synced(istr_map* imap, size_t new_capacity)

    # === Lookup ===
    const istr_entry* c_istr_map_lookup(const istr_map* imap, const char* key, size_t key_length)
    const istr_entry* c_istr_map_lookup_synced(const istr_map* imap, const char* key, size_t key_length)

    # === Intern ===
    const char* c_istr(istr_map* imap, const char* key, size_t key_length, const istr_entry** out_entry)
    const char* c_istr_synced(istr_map* imap, const char* key, size_t key_length, const istr_entry** out_entry)


cdef class InternString:
    cdef readonly InternStringPool pool
    cdef const char* key
    cdef uint64_t hash

    @staticmethod
    cdef InternString c_from_entry(const istr_entry* entry, InternStringPool pool)


cdef class InternStringPool:
    cdef istr_map* pool
    cdef bint owner

    @staticmethod
    cdef InternStringPool c_from_header(const istr_map* header, bint owner=*)

    cpdef InternString istr(self, str string)


cdef class IstrTestToolkit:
    cdef char* buf
    cdef readonly size_t buf_size
    cdef size_t* seg_offsets
    cdef size_t* seg_lengths
    cdef const char** c_keys
    cdef size_t* c_key_lens
    cdef readonly size_t n_seg
    cdef readonly size_t max_seg_len
    cdef readonly size_t n_iters

    cdef readonly InternStringPool pool
    cdef list py_strings
    cdef list py_bytes_list

    cdef inline void c_gen_buf(self)
    cdef inline void c_gen_segments(self)
    cdef inline void c_prepare_py_objects(self)
    cdef inline void c_prepare_istr_pool(self)

    cpdef double istr_hash_routine(self)
    cpdef double istr_intern_routine(self)
    cpdef double istr_intern_synced_routine(self)
    cpdef double istr_lookup_routine(self)
    cpdef double istr_lookup_synced_routine(self)
    cpdef double istr_eq_routine(self)
    cpdef double py_unicode_routine(self)
    cpdef double py_hash_routine(self)
    cpdef double py_eq_routine(self)
    cpdef dict run_test(self)


cdef istr_map* C_POOL
cdef InternStringPool POOL
cdef istr_map* C_INTRA_POOL
cdef InternStringPool INTRA_POOL
