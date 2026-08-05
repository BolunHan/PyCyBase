#ifndef AP_HEAP_C_HEAP_ALLOCATOR_H
#define AP_HEAP_C_HEAP_ALLOCATOR_H

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include "cbase/nt/pthread_nt_compat.h"
#include <intrin.h>
#else
#include <pthread.h>
#endif

// ========== Configuration ==========

#ifndef AP_HEAP_AUTOPAGE_CAPACITY
#define AP_HEAP_AUTOPAGE_CAPACITY (64 * 1024) /* 64 KiB */
#endif

#ifndef AP_HEAP_AUTOPAGE_CAPACITY_MAX
#define AP_HEAP_AUTOPAGE_CAPACITY_MAX (16 * 1024 * 1024) /* 16 MiB */
#endif

#ifndef AP_HEAP_AUTOPAGE_ALIGNMENT
#define AP_HEAP_AUTOPAGE_ALIGNMENT (4 * 1024) /* 4 KiB */
#endif

/* Size-binned free lists: exact 8-byte-granular bins for capacities up to
 * AP_HEAP_EXACT_BIN_COUNT * 8 bytes, pow2-class bins above. */
#ifndef AP_HEAP_EXACT_BIN_COUNT
#define AP_HEAP_EXACT_BIN_COUNT 8192 /* capacity <= 64 KiB gets an exact bin */
#endif

#ifndef AP_HEAP_LARGE_BIN_COUNT
#define AP_HEAP_LARGE_BIN_COUNT 9 /* pow2-class bins for capacity > 64 KiB */
#endif

#define AP_HEAP_BIN_COUNT (AP_HEAP_EXACT_BIN_COUNT + AP_HEAP_LARGE_BIN_COUNT + 1)

/* Miss-path page scaling cap: page sizes double from the current page up
 * to this cap; a request larger than the cap forces a bigger page.
 * Used only when AP_HEAP_PAGE_FIT_TO_REQUEST is 0. */
#ifndef AP_HEAP_PAGE_EXTEND_MAX
#define AP_HEAP_PAGE_EXTEND_MAX (128 * 1024 * 1024) /* 128 MiB */
#endif

/* Miss-path page policy: 0 (default) = capped power-of-2 page scaling
 * (see AP_HEAP_PAGE_EXTEND_MAX); 1 = fit the page to the request (floor
 * = autopage_capacity) so rare bin misses never extend oversized pages. */
#ifndef AP_HEAP_PAGE_FIT_TO_REQUEST
#define AP_HEAP_PAGE_FIT_TO_REQUEST 0
#endif

/* On an exact-bin miss, probe up to this many LARGER exact bins before
 * the page path.  A slightly larger block satisfies the request; on free
 * it returns to its own bin (recycling unaffected), and the fragmentation
 * is bounded by the probe range.  0 disables the probe. */
#ifndef AP_HEAP_EXACT_BIN_PROBE_COUNT
#define AP_HEAP_EXACT_BIN_PROBE_COUNT 2
#endif

// ========== Heap Allocator Structs ==========

typedef struct heap_memory_block {
    size_t                    capacity;
    size_t                    size;
    struct heap_memory_block* next_free;
    struct heap_memory_block* next_allocated;
    struct heap_page*         parent_page;
    char                      buffer[];
} heap_memory_block;

typedef struct heap_page {
    size_t                    capacity;
    size_t                    occupied;
    struct heap_allocator*    allocator;
    struct heap_page*         prev;
    struct heap_memory_block* allocated;
    char                      buffer[];
} heap_page;

typedef struct heap_allocator {
    pthread_mutex_t           lock;
    size_t                    mapped_pages;
    struct heap_page*         active_page;
    size_t                    autopage_capacity;
    size_t                    autopage_capacity_max;
    size_t                    autopage_alignment;
    struct heap_memory_block* bins[AP_HEAP_BIN_COUNT];
} heap_allocator;

// ========== Utility Functions ==========

static inline size_t c_heap_page_roundup(heap_allocator* allocator, size_t size) {
    return (size + allocator->autopage_alignment - 1) & ~(allocator->autopage_alignment - 1);
}

static inline size_t c_heap_block_roundup(size_t size) {
    return (size + sizeof(void*) - 1) & ~(sizeof(void*) - 1);
}

/* ceil(log2(v)) for 0 < v <= UINT32_MAX (portable; intrinsics on MSVC/GCC-Clang).
 * 32-bit is sufficient: the bin structure caps block capacities well below
 * 4 GiB, so a narrower parameter type truthfully advertises the domain. */
static inline size_t c_heap_block_ceil_log2(uint32_t v) {
    size_t floor;
#if defined(_MSC_VER)
    unsigned long idx = 0;
    _BitScanReverse(&idx, (unsigned long) v);
    floor = (size_t) idx;
#else
    floor = (size_t) (31u - __builtin_clz((unsigned int) v));
#endif
    return floor + (v != ((size_t) 1u << floor));
}

/* Size bin for a block capacity (always a multiple of 8).
 * Exact bins: index = capacity / 8 (1..AP_HEAP_EXACT_BIN_COUNT), so any
 * block in bin(cap_net) has capacity == cap_net and always fits.
 * Larger capacities: pow2-class bins keyed by ceil(log2(capacity))
 * (indices AP_HEAP_EXACT_BIN_COUNT+1..); the last bin is the overflow
 * class.  In-bin first-fit is used there (blocks can be up to one class
 * smaller than the request). */
static inline size_t c_heap_block_bin(size_t capacity) {
    if (capacity <= (size_t) AP_HEAP_EXACT_BIN_COUNT * 8u) {
        return capacity >> 3;
    }
    size_t idx = (size_t) AP_HEAP_EXACT_BIN_COUNT + (c_heap_block_ceil_log2(capacity) - 16u);
    if (idx > (size_t) AP_HEAP_EXACT_BIN_COUNT + AP_HEAP_LARGE_BIN_COUNT) {
        idx = (size_t) AP_HEAP_EXACT_BIN_COUNT + AP_HEAP_LARGE_BIN_COUNT;
    }
    return idx;
}

static inline void c_heap_page_reclaim(heap_allocator* allocator, heap_page* page) {
    if (!allocator || !page) {
        errno = EINVAL;
        return;
    }

    heap_memory_block** prevp = &page->allocated;
    while (*prevp) {
        heap_memory_block* block = *prevp;
        if (block->size != 0) {
            break;
        }

        *prevp = block->next_allocated;
        block->next_allocated = NULL;

        heap_memory_block** free_prev = &allocator->bins[c_heap_block_bin(block->capacity)];
        while (*free_prev && *free_prev != block) {
            free_prev = &(*free_prev)->next_free;
        }
        if (*free_prev == block) {
            *free_prev = block->next_free;
        }
        block->next_free = NULL;

        size_t cap_total = block->capacity + sizeof(heap_memory_block);
        if (page->occupied >= cap_total) {
            page->occupied -= cap_total;
        }
    }
}

// ========== Public API Functions ==========

static inline heap_page* c_heap_allocator_extend(heap_allocator* allocator, size_t capacity, pthread_mutex_t* lock) {
    if (!allocator) {
        errno = EINVAL;
        return NULL;
    }

    uint8_t locked = 0;

    if (lock) {
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return NULL;
        }
        locked = 1;
    }

    if (capacity == 0) {
        if (!allocator->active_page) {
            capacity = allocator->autopage_capacity;
        }
        else {
            size_t prev_cap = allocator->active_page->capacity;
            capacity = prev_cap * 2;
            if (capacity < allocator->autopage_capacity) {
                capacity = allocator->autopage_capacity;
            }
            else if (capacity > allocator->autopage_capacity_max) {
                capacity = allocator->autopage_capacity_max;
            }
        }
    }

    size_t     total_capacity = c_heap_page_roundup(allocator, capacity);

    heap_page* page = (heap_page*) calloc(1, total_capacity);

    if (!page) {
        if (locked) pthread_mutex_unlock(lock);
        return NULL;
    }

    page->capacity = total_capacity;
    page->occupied = sizeof(heap_page);
    page->allocator = allocator;
    page->allocated = NULL;
    page->prev = allocator->active_page;
    allocator->active_page = page;
    allocator->mapped_pages++;

    if (locked) pthread_mutex_unlock(lock);
    return page;
}

static inline heap_allocator* c_heap_allocator_new() {
    heap_allocator* allocator = (heap_allocator*) calloc(1, sizeof(heap_allocator));
    if (!allocator) {
        return NULL;
    }

    if (pthread_mutex_init(&allocator->lock, NULL) != 0) {
        free(allocator);
        return NULL;
    }

    allocator->mapped_pages = 0;
    allocator->active_page = NULL;
    allocator->autopage_capacity = AP_HEAP_AUTOPAGE_CAPACITY;
    allocator->autopage_capacity_max = AP_HEAP_AUTOPAGE_CAPACITY_MAX;
    allocator->autopage_alignment = AP_HEAP_AUTOPAGE_ALIGNMENT;

    return allocator;
}

static inline void c_heap_allocator_free(heap_allocator* allocator) {
    if (!allocator) {
        return;
    }

    heap_page* page = allocator->active_page;
    while (page) {
        heap_page* prev = page->prev;
        free(page);
        page = prev;
    }

    pthread_mutex_destroy(&allocator->lock);
    free(allocator);
}

static inline void* c_heap_calloc(heap_allocator* allocator, size_t size, pthread_mutex_t* lock) {
    if (!allocator || size == 0) {
        errno = EINVAL;
        return NULL;
    }

    size_t           cap_net = c_heap_block_roundup(size);
    size_t           overhead = sizeof(heap_memory_block);
    size_t           cap_total = cap_net + overhead;

    uint8_t          locked = 0;
    pthread_mutex_t* builtin_lock = &allocator->lock;
    pthread_mutex_t* child_lock = &allocator->lock;
    if (lock) {
        if (lock == builtin_lock) {
            child_lock = NULL;
        }
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return NULL;
        }
        locked = 1;
    }
    else {
        child_lock = NULL;
    }

    heap_page* page = allocator->active_page;
    if (!page) {
        size_t target_cap = allocator->autopage_capacity;
        while (target_cap < cap_total + sizeof(heap_page)) {
            target_cap *= 2;
        }

        page = c_heap_allocator_extend(allocator, target_cap, child_lock);
        if (!page) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
    }

    if (page->occupied + cap_total > page->capacity) {
        size_t target_cap = page->capacity;

        if (target_cap < allocator->autopage_capacity) {
            target_cap = allocator->autopage_capacity;
        }
        else if (target_cap < allocator->autopage_capacity_max) {
            target_cap *= 2;
        }

        while (target_cap < cap_total + sizeof(heap_page)) {
            target_cap *= 2;
        }
        page = c_heap_allocator_extend(allocator, target_cap, child_lock);
        if (!page) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
    }

    size_t             offset = page->occupied;
    heap_memory_block* block = (heap_memory_block*) ((char*) page + offset);
    block->capacity = cap_net;
    block->size = size;
    block->next_free = NULL;

    block->parent_page = page;
    block->next_allocated = page->allocated;
    page->allocated = block;
    page->occupied += cap_total;

    if (locked) pthread_mutex_unlock(lock);

    memset(block + 1, 0, cap_net);
    return (void*) block->buffer;
}

static inline void* c_heap_request(heap_allocator* allocator, size_t size, int scan_all_pages, pthread_mutex_t* lock) {
    if (!allocator || size == 0) {
        errno = EINVAL;
        return NULL;
    }

    size_t           cap_net = c_heap_block_roundup(size);
    size_t           overhead = sizeof(heap_memory_block);
    size_t           cap_total = cap_net + overhead;

    uint8_t          locked = 0;
    pthread_mutex_t* builtin_lock = &allocator->lock;
    pthread_mutex_t* child_lock = &allocator->lock;
    if (lock) {
        if (lock == builtin_lock) {
            child_lock = NULL;
        }
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return NULL;
        }
        locked = 1;
    }
    else {
        child_lock = NULL;
    }

    /* Step 1: size-binned free-list reuse (see c_heap_block_bin).
     * Exact bins always fit (capacity == cap_net) — O(1) head pop.
     * Pow2-class bins use in-bin first-fit: bins are short and same-
     * shaped, so the head is the common hit; larger-capacity blocks in
     * the bin also satisfy smaller requests. */
    size_t             bin = c_heap_block_bin(cap_net);
    heap_memory_block* free_blk;
    if (bin <= (size_t) AP_HEAP_EXACT_BIN_COUNT) {
        size_t found = bin;
        free_blk = allocator->bins[bin];
        if (!free_blk && AP_HEAP_EXACT_BIN_PROBE_COUNT > 0) {
            size_t probe_end = bin + (size_t) AP_HEAP_EXACT_BIN_PROBE_COUNT;
            if (probe_end > (size_t) AP_HEAP_EXACT_BIN_COUNT) {
                probe_end = (size_t) AP_HEAP_EXACT_BIN_COUNT;
            }
            for (size_t b = bin + 1; b <= probe_end; b++) {
                free_blk = allocator->bins[b];
                if (free_blk) {
                    found = b;
                    break;
                }
            }
        }
        if (free_blk) {
            allocator->bins[found] = free_blk->next_free;
            free_blk->next_free = NULL;
            free_blk->size = size;
            if (locked) pthread_mutex_unlock(lock);
            memset(free_blk + 1, 0, cap_net);
            return (void*) free_blk->buffer;
        }
    }
    else {
        heap_memory_block** prevp = &allocator->bins[bin];
        free_blk = *prevp;
        while (free_blk) {
            if (free_blk->capacity >= cap_net) {
                *prevp = free_blk->next_free;
                free_blk->next_free = NULL;
                free_blk->size = size;
                if (locked) pthread_mutex_unlock(lock);
                memset(free_blk + 1, 0, cap_net);
                return (void*) free_blk->buffer;
            }
            prevp = &free_blk->next_free;
            free_blk = free_blk->next_free;
        }
    }

    heap_page* target_page = NULL;
    if (scan_all_pages) {
        heap_page* iter = allocator->active_page;
        while (iter) {
            if (iter->occupied + cap_total <= iter->capacity) {
                target_page = iter;
                break;
            }
            iter = iter->prev;
        }
    }
    else if (allocator->active_page) {
        heap_page* meta = allocator->active_page;
        if (meta && meta->occupied + cap_total <= meta->capacity) {
            target_page = allocator->active_page;
        }
    }

    if (!target_page) {
        size_t target_cap;
#if AP_HEAP_PAGE_FIT_TO_REQUEST
        /* Fit the page to the request (floor = autopage_capacity): rare
         * bin misses must not extend oversized pages. */
        target_cap = allocator->autopage_capacity;
#else
        /* Page scaling with a cap: double from the current page size up to
         * AP_HEAP_PAGE_EXTEND_MAX.  A page larger than the cap (e.g. from
         * a huge request) scales back down to the cap.  Requests larger
         * than the cap force a bigger page via the fit loop below. */
        heap_page* current = allocator->active_page;
        if (!current) {
            target_cap = allocator->autopage_capacity;
        }
        else {
            target_cap = current->capacity;
            if (target_cap < allocator->autopage_capacity) {
                target_cap = allocator->autopage_capacity;
            }
            else if (target_cap > (size_t) AP_HEAP_PAGE_EXTEND_MAX) {
                target_cap = (size_t) AP_HEAP_PAGE_EXTEND_MAX;
            }
            else if (target_cap < (size_t) AP_HEAP_PAGE_EXTEND_MAX) {
                target_cap *= 2;
                if (target_cap > (size_t) AP_HEAP_PAGE_EXTEND_MAX) {
                    target_cap = (size_t) AP_HEAP_PAGE_EXTEND_MAX;
                }
            }
        }
#endif
        while (target_cap < cap_total + sizeof(heap_page)) {
            target_cap *= 2;
        }

        target_page = c_heap_allocator_extend(allocator, target_cap, child_lock);
        if (!target_page) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
    }

    size_t             offset = target_page->occupied;
    heap_memory_block* block = (heap_memory_block*) ((char*) target_page + offset);
    block->capacity = cap_net;
    block->size = size;
    block->next_free = NULL;

    block->parent_page = target_page;
    block->next_allocated = target_page->allocated;
    target_page->allocated = block;

    target_page->occupied += cap_total;

    if (locked) pthread_mutex_unlock(lock);

    memset(block + 1, 0, cap_net);
    return (void*) block->buffer;
}

static inline void c_heap_free(void* ptr, pthread_mutex_t* lock) {
    if (!ptr) {
        errno = EINVAL;
        return;
    }

    heap_memory_block* block = (heap_memory_block*) ((char*) ptr - sizeof(heap_memory_block));
    heap_page*         page = block->parent_page;
    if (!page || !page->allocator) {
        errno = EINVAL;
        return;
    }

    heap_allocator* allocator = page->allocator;

    uint8_t         locked = 0;
    if (lock) {
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return;
        }
        locked = 1;
    }

    block->size = 0;
    size_t bin = c_heap_block_bin(block->capacity);
    block->next_free = allocator->bins[bin];
    allocator->bins[bin] = block;

    if (locked) pthread_mutex_unlock(lock);
}

static inline void c_heap_reclaim(heap_allocator* allocator, pthread_mutex_t* lock) {
    if (!allocator) {
        errno = EINVAL;
        return;
    }

    uint8_t locked = 0;
    if (lock) {
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return;
        }
        locked = 1;
    }

    heap_page* page = allocator->active_page;
    while (page) {
        c_heap_page_reclaim(allocator, page);
        page = page->prev;
    }

    if (locked) pthread_mutex_unlock(lock);
}

#endif /* AP_HEAP_C_HEAP_ALLOCATOR_H */
