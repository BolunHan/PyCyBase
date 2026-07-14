# c_shm_comp.pxd — Cython declarations for the platform-dispatch SHM compat layer.
#
# All platform branching happens in c_shm_comp.h (C preprocessor).
# This .pxd file contains no IF UNAME_SYSNAME conditionals.
#
# Type names MUST match the C names in c_shm_comp.h (shm_allocator, shm_allocator_ctx)
# so that they are the same Cython type as the platform-specific .pxd declarations.


cdef extern from "cbase/allocator_protocol/c_shm_comp.h":
    # -- Types (common subset used by c_allocator_protocol) -------------------
    #
    # Type names match the C typedefs — same as c_shm_allocator.h (POSIX)
    # and the aliases in c_shm_comp.h (Windows).  This ensures they are the
    # same Cython type as the platform-specific .pxd declarations.

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
