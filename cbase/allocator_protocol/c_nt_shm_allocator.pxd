from libc.stdint cimport uintptr_t

# Windows DWORD type
cdef extern from "<windows.h>":
    ctypedef unsigned long DWORD

cdef extern from "cbase/nt/pthread_nt_compat.h":
    ctypedef struct pthread_mutex_t:
        pass

    int pthread_mutex_init(pthread_mutex_t* mutex, void* attr)
    int pthread_mutex_lock(pthread_mutex_t* mutex)
    int pthread_mutex_unlock(pthread_mutex_t* mutex)
    int pthread_mutex_destroy(pthread_mutex_t* mutex)

cdef extern from "cbase/allocator_protocol/c_nt_shm_allocator.h":
    const size_t AP_SHM_AUTOPAGE_CAPACITY
    const size_t AP_SHM_AUTOPAGE_CAPACITY_MAX
    const size_t AP_SHM_AUTOPAGE_ALIGNMENT
    const char* AP_SHM_ALLOCATOR_PREFIX
    const size_t AP_SHM_NAME_LEN
    const size_t AP_SHM_PREFIX_MAX
    const size_t AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE
    const size_t c_nt_shm_page_overhead
    const size_t c_nt_shm_block_overhead

    ctypedef struct nt_shm_page:
        size_t capacity
        size_t occupied
        size_t offset
        nt_shm_allocator* allocator
        nt_shm_memory_block* allocated
        char shm_name[AP_SHM_NAME_LEN]
        char prev_name[AP_SHM_NAME_LEN]

    ctypedef struct nt_shm_page_ctx:
        nt_shm_page* shm_page
        void* handle
        char* buffer
        nt_shm_page_ctx* prev

    ctypedef struct nt_shm_memory_block:
        size_t capacity
        size_t size
        nt_shm_memory_block* next_free
        nt_shm_memory_block* next_allocated
        nt_shm_page* parent_page
        char buffer[]

    ctypedef struct nt_shm_allocator:
        char shm_name[AP_SHM_NAME_LEN]
        size_t pid
        char lock_name[AP_SHM_NAME_LEN]
        size_t mapped_size
        char active_page[AP_SHM_NAME_LEN]
        size_t mapped_pages
        nt_shm_memory_block* free_list
        size_t autopage_capacity
        size_t autopage_capacity_max
        size_t autopage_alignment
        char shm_prefix[AP_SHM_PREFIX_MAX]
        pthread_mutex_t lock

    ctypedef struct nt_shm_allocator_ctx:
        nt_shm_allocator* shm_allocator
        void* shm_handle
        void* lock_handle
        nt_shm_page_ctx* active_page

    size_t c_nt_shm_page_roundup(nt_shm_allocator* allocator, size_t size)
    size_t c_nt_shm_block_roundup(size_t size)
    void c_nt_shm_allocator_name(const char* shm_prefix, char* out)
    void c_nt_shm_page_name(nt_shm_allocator* allocator, char* out)
    void c_nt_shm_mutex_name(const char* shm_prefix, char* out)
    int c_nt_shm_scan(const char* prefix, const char* suffix, char* out, size_t out_len)
    nt_shm_page_ctx* c_nt_shm_page_new(nt_shm_allocator* allocator, size_t page_capacity)
    int c_nt_shm_page_map(nt_shm_allocator* allocator, nt_shm_page_ctx* page_ctx)
    void c_nt_shm_page_reclaim(nt_shm_allocator* allocator, nt_shm_page_ctx* page_ctx)

    nt_shm_page_ctx* c_nt_shm_allocator_extend(nt_shm_allocator_ctx* ctx, size_t capacity, pthread_mutex_t* lock)
    nt_shm_allocator_ctx* c_nt_shm_allocator_new(size_t region_size, const char* shm_prefix)
    void c_nt_shm_allocator_free(nt_shm_allocator_ctx* ctx)
    void* c_nt_shm_calloc(nt_shm_allocator_ctx* ctx, size_t size, pthread_mutex_t* lock)
    void* c_nt_shm_request(nt_shm_allocator_ctx* ctx, size_t size, int scan_all_pages, pthread_mutex_t* lock)
    void c_nt_shm_free(void* ptr, pthread_mutex_t* lock)
    void c_nt_shm_reclaim(nt_shm_allocator_ctx* ctx, pthread_mutex_t* lock)
    int c_nt_shm_scan_allocator(const char* shm_prefix, char* out)
    int c_nt_shm_scan_page(const char* shm_prefix, char* out)
    DWORD c_nt_shm_pid(const char* shm_name)
    nt_shm_allocator* c_nt_shm_allocator_dangling(const char* shm_prefix, char* shm_name)
    void c_nt_shm_clear_dangling(const char* shm_prefix)


cdef class NtSharedMemoryAllocator:
    cdef nt_shm_allocator_ctx* ctx
    cdef readonly bint owner

    cdef inline void* c_calloc(self, size_t size, pthread_mutex_t* lock=?)
    cdef inline void* c_request(self, size_t size, int scan_all_pages=?, pthread_mutex_t* lock=?)
    cdef inline void c_free(self, void* ptr, pthread_mutex_t* lock=?)

    cpdef object calloc(self, size_t size, bint with_lock=?)
    cpdef object request(self, size_t size, bint scan_all_pages=?, bint with_lock=?)
    cpdef void free(self, object buffer, bint with_lock=?)
    cpdef void reclaim(self, bint with_lock=?)
    cpdef object extend(self, size_t capacity=?, bint with_lock=?)
