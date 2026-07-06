from libc.stdint cimport int64_t, uint64_t, uint8_t
from libcpp cimport bool as c_bool

from .c_heap_allocator cimport heap_allocator as heap_allocator_t
from .c_shm_allocator cimport shm_allocator as shm_allocator_t, shm_allocator_ctx as shm_allocator_ctx_t


cdef extern from "cbase/allocator_protocol/c_allocator_protocol.h":
    uint8_t AP_ALLOC_VIGILANT
    uint64_t AP_ALLOC_MAGIC

    ctypedef struct allocator_protocol:
        shm_allocator_t* shm_allocator
        shm_allocator_ctx_t* shm_allocator_ctx
        heap_allocator_t* heap_allocator
        c_bool with_lock
        c_bool with_shm
        c_bool with_freelist
        size_t size
        uint64_t magic
        int64_t ref_count
        char buf[]

    allocator_protocol* c_ap_allocator_protocol_new(size_t size, shm_allocator_ctx_t* shm_allocator, heap_allocator_t* heap_allocator, c_bool with_lock) noexcept nogil
    void c_ap_allocator_protocol_free(allocator_protocol* protocol) noexcept nogil
    int64_t c_ap_allocator_protocol_acquire_owner(allocator_protocol* protocol) noexcept nogil
    int64_t c_ap_allocator_protocol_release_owner(allocator_protocol* protocol) noexcept nogil

    allocator_protocol* c_ap_protocol_from_ptr(const void* ptr) noexcept nogil
    void* c_ap_alloc(size_t size, allocator_protocol* schematic) noexcept nogil
    void c_ap_free(void* ptr) noexcept nogil
    void c_ap_incref(void* ptr) noexcept nogil
    void c_ap_decref(void* ptr) noexcept nogil
    char* c_ap_strdup(const char* src, allocator_protocol* allocator) noexcept nogil
    void* c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator) noexcept nogil


cdef bint AP_CFG_LOCKED
cdef bint AP_CFG_SHARED
cdef bint AP_CFG_FREELIST


cdef class EnvConfigContext:
    cdef dict overrides
    cdef dict originals

    cdef void c_activate(self)

    cdef void c_deactivate(self)


cdef EnvConfigContext AP_SHARED
cdef EnvConfigContext AP_LOCKED
cdef EnvConfigContext AP_FREELIST


cdef class AllocatorProtocol:
    cdef allocator_protocol* protocol

    @staticmethod
    cdef AllocatorProtocol c_from_protocol(allocator_protocol* protocol)


cdef allocator_protocol* AP_DEFAULT_ALLOCATOR
cdef allocator_protocol* AP_SHM_ALLOCATOR
cdef allocator_protocol* AP_HEAP_ALLOCATOR
