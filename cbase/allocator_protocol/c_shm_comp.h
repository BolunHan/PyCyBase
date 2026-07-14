#ifndef C_SHM_COMP_H
#define C_SHM_COMP_H

/**
 * c_shm_comp.h — Platform-dispatch compatibility header for SHM allocators.
 *
 * On POSIX:   includes c_shm_allocator.h directly.
 * On Windows: includes c_nt_shm_allocator.h and aliases nt_shm_* → shm_*.
 *
 * This header exists so that Cython .pxd / .pyx files can declare SHM types
 * via a single `cdef extern from "cbase/allocator_protocol/c_shm_comp.h"`
 * without IF UNAME_SYSNAME branching.
 */

#ifdef _WIN32
#include "cbase/allocator_protocol/c_nt_shm_allocator.h"

typedef nt_shm_allocator      shm_allocator;
typedef nt_shm_allocator_ctx  shm_allocator_ctx;
typedef nt_shm_page           shm_page;
typedef nt_shm_page_ctx       shm_page_ctx;
typedef nt_shm_memory_block   shm_memory_block;

// Function aliases — NT implementations have identical signatures
#define c_shm_request        c_nt_shm_request
#define c_shm_calloc         c_nt_shm_calloc
#define c_shm_free           c_nt_shm_free
#define c_shm_reclaim        c_nt_shm_reclaim
#define c_shm_allocator_new  c_nt_shm_allocator_new
#define c_shm_allocator_free c_nt_shm_allocator_free

#else
#include "cbase/allocator_protocol/c_shm_allocator.h"
#endif

#endif  // C_SHM_COMP_H
