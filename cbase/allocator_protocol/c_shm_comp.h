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

typedef nt_shm_allocator     shm_allocator;
typedef nt_shm_allocator_ctx shm_allocator_ctx;
typedef nt_shm_page          shm_page;
typedef nt_shm_page_ctx      shm_page_ctx;
typedef nt_shm_memory_block  shm_memory_block;

// Static inline wrappers — visible to Cython .pxd files (unlike #define macros).
static inline shm_allocator_ctx* c_shm_allocator_new(size_t region_size, const char* shm_prefix) {
    return (shm_allocator_ctx*) c_nt_shm_allocator_new(region_size, shm_prefix);
}
static inline void c_shm_allocator_free(shm_allocator_ctx* ctx) {
    c_nt_shm_allocator_free((nt_shm_allocator_ctx*) ctx);
}
static inline void* c_shm_calloc(shm_allocator_ctx* ctx, size_t size, pthread_mutex_t* lock) {
    return c_nt_shm_calloc((nt_shm_allocator_ctx*) ctx, size, lock);
}
static inline void* c_shm_request(shm_allocator_ctx* ctx, size_t size, int scan_all_pages, pthread_mutex_t* lock) {
    return c_nt_shm_request((nt_shm_allocator_ctx*) ctx, size, scan_all_pages, lock);
}
static inline void c_shm_free(void* ptr, pthread_mutex_t* lock) {
    c_nt_shm_free(ptr, lock);
}
static inline void c_shm_reclaim(shm_allocator_ctx* ctx, pthread_mutex_t* lock) {
    c_nt_shm_reclaim((nt_shm_allocator_ctx*) ctx, lock);
}

#else
#include "cbase/allocator_protocol/c_shm_allocator.h"
// Functions are already defined in c_shm_allocator.h — no wrappers needed.
#endif

#endif  // C_SHM_COMP_H
