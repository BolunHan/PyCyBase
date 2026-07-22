#ifndef C_ALLOCATOR_PROTOCOL_H
#define C_ALLOCATOR_PROTOCOL_H

#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include <cbase/allocator_protocol/c_heap_allocator.h>

#ifdef _WIN32
#include <cbase/allocator_protocol/c_nt_shm_allocator.h>
// Type aliases -- NT structs masquerade as POSIX names
typedef nt_shm_allocator     shm_allocator;
typedef nt_shm_allocator_ctx shm_allocator_ctx;
typedef nt_shm_page          shm_page;
typedef nt_shm_page_ctx      shm_page_ctx;
typedef nt_shm_memory_block  shm_memory_block;
// Function aliases -- NT implementations with identical signatures
#define c_shm_allocator_new c_nt_shm_allocator_new
#define c_shm_allocator_free c_nt_shm_allocator_free
#define c_shm_request c_nt_shm_request
#define c_shm_calloc c_nt_shm_calloc
#define c_shm_free c_nt_shm_free
#define c_shm_reclaim c_nt_shm_reclaim
#else
#include <cbase/allocator_protocol/c_shm_allocator.h>
#endif

// ========== Constants ==========

#ifndef AP_ALLOC_VIGILANT
#define AP_ALLOC_VIGILANT 1
#endif

#ifndef AP_ALLOC_MAGIC
#define AP_ALLOC_MAGIC 0xCFBBBBFCULL
#endif

#ifndef AP_DEALLOC_MAGIC
#define AP_DEALLOC_MAGIC 0xDEADDEADULL
#endif

#ifndef AP_DECREF_AUTOFREE
#define AP_DECREF_AUTOFREE 1
#endif

#ifndef AP_ALLOC_WITH_LOCK
#define AP_ALLOC_WITH_LOCK 1
#endif

#ifndef AP_ALLOC_WITH_SHM
#define AP_ALLOC_WITH_SHM 0
#endif

#ifndef AP_ALLOC_WITH_FREELIST
#define AP_ALLOC_WITH_FREELIST 1
#endif

// ========== Structs ==========

typedef struct allocator_protocol {
    shm_allocator*     shm_allocator;
    shm_allocator_ctx* shm_allocator_ctx;
    heap_allocator*    heap_allocator;
    bool               with_lock;
    bool               with_shm;
    bool               with_freelist;
    size_t             size;
#if AP_ALLOC_VIGILANT > 0
    uint64_t magic;
#endif
    _Atomic int64_t ref_count;
    char            buf[];
} allocator_protocol;

// ========== Forward Declaration ==========

static inline allocator_protocol* c_ap_allocator_protocol_new(size_t size, shm_allocator_ctx* shm_allocator, heap_allocator* heap_allocator, bool with_lock);
static inline void                c_ap_allocator_protocol_free(allocator_protocol* protocol);
static inline int64_t             c_ap_allocator_protocol_acquire_owner(allocator_protocol* protocol);
static inline int64_t             c_ap_allocator_protocol_release_owner(allocator_protocol* protocol);

static inline allocator_protocol* c_ap_protocol_from_ptr(const void* ptr);
static inline void*               c_ap_alloc(size_t size, allocator_protocol* schematic);
static inline void                c_ap_free(void* ptr);
static inline void                c_ap_incref(void* ptr);
static inline void                c_ap_decref(void* ptr);
static inline char*               c_ap_strdup(const char* src, allocator_protocol* allocator);
static inline void*               c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator);
static inline bool                c_ap_is_allocator_buf(const void* ptr);

// ========== Utilities Functions ==========

static inline allocator_protocol* c_ap_allocator_protocol_new(size_t size, shm_allocator_ctx* shm_allocator, heap_allocator* heap_allocator, bool with_lock) {
    if (size == 0) return NULL;
    size_t              ttl_size = sizeof(allocator_protocol) + size;
    allocator_protocol* protocol;

    if (shm_allocator) {
        pthread_mutex_t* lock = with_lock ? &shm_allocator->shm_allocator->lock : NULL;
        protocol = (allocator_protocol*) c_shm_request(shm_allocator, ttl_size, 0, lock);
        if (!protocol) return NULL;
        protocol->shm_allocator = shm_allocator->shm_allocator;
        protocol->shm_allocator_ctx = shm_allocator;
        protocol->with_lock = with_lock;
        protocol->with_shm = true;
    }
    else if (heap_allocator) {
        pthread_mutex_t* lock = with_lock ? &heap_allocator->lock : NULL;
        protocol = (allocator_protocol*) c_heap_request(heap_allocator, ttl_size, 0, lock);
        if (!protocol) return NULL;
        protocol->heap_allocator = heap_allocator;
        protocol->with_lock = with_lock;
        protocol->with_freelist = true;
    }
    else {
        protocol = (allocator_protocol*) calloc(1, ttl_size);
        if (!protocol) return NULL;
    }

    protocol->with_lock = with_lock;
    protocol->size = size;
    // _new method DOES NOT manipulate ref_count! So as the _free method.
    // atomic_store_explicit(&protocol->ref_count, 1, memory_order_release);

#if AP_ALLOC_VIGILANT > 0
    protocol->magic = AP_ALLOC_MAGIC;
#endif

    return protocol;
}

static inline void c_ap_allocator_protocol_free(allocator_protocol* protocol) {
    if (!protocol) return;

#if AP_ALLOC_VIGILANT > 0
    // Invalidate magic to catch double free or invalid free attempts
    protocol->magic = AP_DEALLOC_MAGIC;
#endif
    bool with_lock = protocol->with_lock;
    bool with_shm = protocol->with_shm;
    bool with_freelist = protocol->with_freelist;

    // _free method DOES NOT manipulate ref_count! So as the _new method.
    // atomic_store_explicit(&protocol->ref_count, 0, memory_order_release);

    if (with_shm && with_freelist) {
        fprintf(stderr, "[c_ap_allocator_protocol_free] ERROR: Protocol cannot have both with_shm and with_freelist set to true!\n");
        abort();
    }
    else if (with_shm) {
        shm_allocator*   shm_allocator = protocol->shm_allocator;
        pthread_mutex_t* lock = with_lock ? &shm_allocator->lock : NULL;
        c_shm_free((void*) protocol, lock);
    }
    else if (with_freelist) {
        heap_allocator*  heap_allocator = protocol->heap_allocator;
        pthread_mutex_t* lock = with_lock ? &heap_allocator->lock : NULL;
        c_heap_free((void*) protocol, lock);
    }
    else {
        free((void*) protocol);
    }
}

static inline int64_t c_ap_allocator_protocol_acquire_owner(allocator_protocol* protocol) {
    if (!protocol) return 0;
    return atomic_fetch_add_explicit(&protocol->ref_count, 1, memory_order_acq_rel) + 1;
}

static inline int64_t c_ap_allocator_protocol_release_owner(allocator_protocol* protocol) {
    if (!protocol) return 0;
    return atomic_fetch_sub_explicit(&protocol->ref_count, 1, memory_order_acq_rel) - 1;
}

// ========== Public APIs ==========

static inline allocator_protocol* c_ap_protocol_from_ptr(const void* ptr) {
    if (!ptr) return NULL;
    allocator_protocol* protocol = (allocator_protocol*) ((char*) ptr - offsetof(allocator_protocol, buf));
#if AP_ALLOC_VIGILANT > 0
    if (protocol->magic != AP_ALLOC_MAGIC) {
        if (protocol->magic == AP_DEALLOC_MAGIC) {
            fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: Use-after-free detected in c_ap_protocol_from_ptr!\n");
            fprintf(stderr, "[AP_ALLOC_VIGILANT] Pointer %p was already freed (dealloc magic: 0x%llx).\n", ptr, (unsigned long long) AP_DEALLOC_MAGIC);
        }
        else {
            fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: Magic mismatch in c_ap_protocol_from_ptr! Not an ap-allocated pointer!\n");
            fprintf(stderr, "[AP_ALLOC_VIGILANT] Expected: 0x%llx, Got: 0x%llx\n", (unsigned long long) AP_ALLOC_MAGIC, (unsigned long long) protocol->magic);
            fprintf(stderr, "[AP_ALLOC_VIGILANT] This is likely a raw malloc / calloc'd pointer.\n");
        }
        fflush(stderr);
        abort();
    }
#endif

    return protocol;
}

static inline void* c_ap_alloc(size_t size, allocator_protocol* schematic) {
    allocator_protocol* clone;

    if (!schematic) {
        clone = (allocator_protocol*) calloc(1, sizeof(allocator_protocol) + size);
        if (!clone) return NULL;
        clone->size = size;
        atomic_store_explicit(&clone->ref_count, 1, memory_order_release);
#if AP_ALLOC_VIGILANT > 0
        clone->magic = AP_ALLOC_MAGIC;
#endif
        return (void*) clone->buf;
    }

    if (schematic->with_shm) {
        bool               with_lock = schematic->with_lock;
        shm_allocator_ctx* ctx = schematic->shm_allocator_ctx;
        shm_allocator*     allocator = schematic->shm_allocator;
        pthread_mutex_t*   lock = with_lock ? &allocator->lock : NULL;
        clone = (allocator_protocol*) c_shm_request(ctx, sizeof(allocator_protocol) + size, 0, lock);
        if (!clone) return NULL;
        clone->shm_allocator = allocator;
        clone->shm_allocator_ctx = ctx;
        clone->with_lock = with_lock;
        clone->with_shm = 1;
    }
    else if (schematic->with_freelist) {
        bool             with_lock = schematic->with_lock;
        heap_allocator*  allocator = schematic->heap_allocator;
        pthread_mutex_t* lock = with_lock ? &allocator->lock : NULL;
        clone = (allocator_protocol*) c_heap_request(allocator, sizeof(allocator_protocol) + size, 0, lock);
        if (!clone) return NULL;
        clone->heap_allocator = allocator;
        clone->with_lock = with_lock;
        clone->with_freelist = 1;
    }
    else {
        clone = (allocator_protocol*) calloc(1, sizeof(allocator_protocol) + size);
        if (!clone) return NULL;
    }

    clone->with_lock = schematic->with_lock;
    clone->size = size;
    atomic_store_explicit(&clone->ref_count, 1, memory_order_release);
#if AP_ALLOC_VIGILANT > 0
    clone->magic = AP_ALLOC_MAGIC;
#endif
    return (void*) clone->buf;
}

static inline void c_ap_free(void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);

#if AP_ALLOC_VIGILANT > 0
    if (protocol->magic != AP_ALLOC_MAGIC) {
        if (protocol->magic == AP_DEALLOC_MAGIC) {
            fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: Double free detected in c_ap_free!\n");
            fprintf(stderr, "[AP_ALLOC_VIGILANT] Pointer %p was already freed (dealloc magic: 0x%llx).\n", ptr, (unsigned long long) AP_DEALLOC_MAGIC);
        }
        else {
            fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: Magic mismatch in c_ap_free! Not an ap-allocated pointer!\n");
            fprintf(stderr, "[AP_ALLOC_VIGILANT] Expected: 0x%llx, Got: 0x%llx\n", (unsigned long long) AP_ALLOC_MAGIC, (unsigned long long) protocol->magic);
            fprintf(stderr, "[AP_ALLOC_VIGILANT] This is likely a raw malloc / calloc'd pointer.\n");
        }
        fflush(stderr);
        abort();
    }

    if (atomic_load_explicit(&protocol->ref_count, memory_order_acquire) > 1) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: c_ap_free is not allowed while buffer is shared (ref_count>1)!\n");
        fflush(stderr);
        abort();
    }
#endif

    atomic_store_explicit(&protocol->ref_count, 0, memory_order_release);
    c_ap_allocator_protocol_free(protocol);
}

static inline void c_ap_incref(void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);
    int64_t             ref_count = c_ap_allocator_protocol_acquire_owner(protocol);

#if AP_ALLOC_VIGILANT > 0
    if (ref_count <= 1) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: incref on non-owned allocator protocol (new_ref_count=%lld)!\n", (long long) ref_count);
        fflush(stderr);
        abort();
    }
#endif
}

static inline void c_ap_decref(void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);
    int64_t             ref_count = c_ap_allocator_protocol_release_owner(protocol);

#if AP_ALLOC_VIGILANT > 0
    if (ref_count < 0) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: decref on unowned allocator protocol (new_ref_count=%lld)!\n", (long long) ref_count);
        fflush(stderr);
        abort();
    }
#endif

#if AP_DECREF_AUTOFREE > 0
    if (ref_count == 0) {
        c_ap_allocator_protocol_free(protocol);
    }
#endif
}

static inline char* c_ap_strdup(const char* src, allocator_protocol* allocator) {
    if (!src) return NULL;
    size_t len = strlen(src);
    char*  trg = (char*) c_ap_alloc(len + 1, allocator);
    if (!trg) return NULL;
    memcpy(trg, src, len);
    return trg;
}

static inline void* c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator) {
    if (!src) return c_ap_alloc(new_size, allocator);
    if (new_size == 0) {
        c_ap_free(src);
        return NULL;
    }

    allocator_protocol* protocol = c_ap_protocol_from_ptr(src);
    size_t              copy_size = protocol->size < new_size ? protocol->size : new_size;
    void*               new_ptr = c_ap_alloc(new_size, allocator);
    if (!new_ptr) return NULL;
    memcpy(new_ptr, src, copy_size);
    c_ap_free(src);
    return new_ptr;
}

static inline bool c_ap_is_allocator_buf(const void* ptr) {
    if (!ptr) return false;
#if AP_ALLOC_VIGILANT > 0
    allocator_protocol* protocol = (allocator_protocol*) ((char*) ptr - offsetof(allocator_protocol, buf));
    return protocol->magic == AP_ALLOC_MAGIC;
#else
    (void) ptr;
    return true;
#endif
}

#endif /* C_ALLOCATOR_PROTOCOL_H */