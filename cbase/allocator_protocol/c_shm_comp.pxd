
cdef extern from "cbase/allocator_protocol/c_shm_comp.h":
    # -- Constants -----------------------------------------------------------

    const size_t AP_SHM_AUTOPAGE_CAPACITY
    const size_t AP_SHM_AUTOPAGE_CAPACITY_MAX
    const size_t AP_SHM_AUTOPAGE_ALIGNMENT
    const char*  AP_SHM_ALLOCATOR_PREFIX
    const size_t AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE

    # -- Types ---------------------------------------------------------------

    ctypedef struct pthread_mutex_t:
        pass

    ctypedef struct shm_allocator:
        char            shm_name[256]
        size_t          pid
        pthread_mutex_t lock
        size_t          autopage_capacity
        size_t          autopage_capacity_max
        size_t          autopage_alignment
        char            shm_prefix[64]

    ctypedef struct shm_allocator_ctx:
        shm_allocator* shm_allocator

    # -- Functions (static inline wrappers on Windows, real on POSIX) --------

    shm_allocator_ctx* c_shm_allocator_new(size_t region_size, const char* shm_prefix)
    void               c_shm_allocator_free(shm_allocator_ctx* ctx)
    void*              c_shm_calloc(shm_allocator_ctx* ctx, size_t size, pthread_mutex_t* lock)
    void*              c_shm_request(shm_allocator_ctx* ctx, size_t size, int scan_all_pages, pthread_mutex_t* lock)
    void               c_shm_free(void* ptr, pthread_mutex_t* lock)
    void               c_shm_reclaim(shm_allocator_ctx* ctx, pthread_mutex_t* lock)


cdef shm_allocator_ctx* C_SHM_COMP
