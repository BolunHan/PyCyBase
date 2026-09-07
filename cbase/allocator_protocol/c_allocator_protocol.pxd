from libc.stdint cimport int64_t, uint64_t, uint8_t, uintptr_t
from libcpp cimport bool as c_bool

from cbase.env cimport EnvConfigContext

from .c_heap_allocator cimport heap_allocator as heap_allocator_t
from .c_shm_comp cimport shm_allocator as shm_allocator_t, shm_allocator_ctx as shm_allocator_ctx_t


cdef extern from "cbase/allocator_protocol/c_allocator_protocol.h":
    const uint8_t AP_ALLOC_VIGILANT
    const uint64_t AP_ALLOC_MAGIC
    const uint64_t AP_DEALLOC_MAGIC
    const uint8_t AP_DECREF_AUTOFREE
    const c_bool AP_ALLOC_WITH_LOCK
    const c_bool AP_ALLOC_WITH_SHM
    const c_bool AP_ALLOC_WITH_FREELIST

    ctypedef enum ap_callback_event:
        AP_CALLBACK_EVENT_NEW
        AP_CALLBACK_EVENT_FREE
        AP_CALLBACK_EVENT_INIT
        AP_CALLBACK_EVENT_DEALLOC
        AP_CALLBACK_EVENT_CLEAR
        AP_CALLBACK_EVENT_INCREF
        AP_CALLBACK_EVENT_DECREF
        AP_CALLBACK_EVENT_NOREF
        AP_CALLBACK_EVENT_ACQUIRE_OWNERSHIP
        AP_CALLBACK_EVENT_RELEASE_OWNERSHIP

    ctypedef void (*ap_callback_func)(ap_callback_event event, void* buf, void* user_data) noexcept

    ctypedef struct ap_callback_ctx:
        ap_callback_func fn
        void* user_data
        uintptr_t id
        ap_callback_ctx* next

    ctypedef enum ap_ret_code:
        AP_OK
        AP_ERR_INVALID_ARG
        AP_ERR_OOM
        AP_ERR_NOT_FOUND

    ctypedef struct allocator_protocol:
        shm_allocator_t* shm_allocator
        shm_allocator_ctx_t* shm_allocator_ctx
        heap_allocator_t* heap_allocator
        ap_callback_ctx* callbacks
        c_bool with_lock
        c_bool with_shm
        c_bool with_freelist
        size_t size
        uint64_t magic
        int64_t ref_count
        char buf[]

    allocator_protocol* c_ap_allocator_protocol_new(size_t size, shm_allocator_ctx_t* shm_allocator, heap_allocator_t* heap_allocator, c_bool with_lock) noexcept nogil
    void c_ap_allocator_protocol_free(allocator_protocol* protocol) noexcept nogil
    void c_ap_invoke_callbacks(allocator_protocol* protocol, ap_callback_event event) noexcept nogil

    allocator_protocol* c_ap_protocol_from_ptr(const void* ptr) noexcept nogil
    void* c_ap_alloc(size_t size, allocator_protocol* schematic) noexcept nogil
    void c_ap_free(void* ptr) noexcept nogil
    void c_ap_incref(const void* ptr) noexcept nogil
    void c_ap_decref(const void* ptr) noexcept nogil
    int64_t c_ap_acquire_ownership(allocator_protocol* protocol) noexcept nogil
    int64_t c_ap_release_ownership(allocator_protocol* protocol) noexcept nogil
    char* c_ap_strdup(const char* src, allocator_protocol* allocator) noexcept nogil
    void* c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator) noexcept nogil
    c_bool c_ap_is_allocator_buf(const void* ptr) noexcept nogil

    int c_ap_register_callback(allocator_protocol* protocol, ap_callback_func callback, void* user_data, uintptr_t* out_id) noexcept nogil
    int c_ap_unregister_callback(allocator_protocol* protocol, uintptr_t callback_id) noexcept nogil


cdef class AllocatorConfigContext(EnvConfigContext):
    cdef allocator_protocol* allocator_schematic

    cdef void c_bind(self, allocator_protocol* schematic=?)


cdef class AllocatorProtocol:
    cdef allocator_protocol* protocol

    @staticmethod
    cdef AllocatorProtocol c_from_protocol(allocator_protocol* protocol)


cdef allocator_protocol* AP_DEFAULT_ALLOCATOR
cdef allocator_protocol* AP_SHM_ALLOCATOR
cdef allocator_protocol* AP_HEAP_ALLOCATOR

cdef AllocatorConfigContext AP_SHARED
cdef AllocatorConfigContext AP_LOCKED
cdef AllocatorConfigContext AP_LOCKFREE
cdef AllocatorConfigContext AP_FREELIST
