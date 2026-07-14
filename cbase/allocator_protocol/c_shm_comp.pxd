
cdef extern from "cbase/allocator_protocol/c_shm_comp.h":
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


cdef shm_allocator_ctx* C_SHM_COMP
