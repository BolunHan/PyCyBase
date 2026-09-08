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

// clang-format off

typedef enum ap_callback_event {
    // Schematic Event (0x00)
    AP_CALLBACK_EVENT_NEW               = 0x0000,
    // Lifecycle Management (0x00)
    AP_CALLBACK_EVENT_FREE              = 0x0001,
    AP_CALLBACK_EVENT_INIT              = 0x0002,
    AP_CALLBACK_EVENT_DEALLOC           = 0x0003,
    // Content Management (0x01)
    AP_CALLBACK_EVENT_CLEAR             = 0x0101,
    // Ref Counting Update (0x02)
    AP_CALLBACK_EVENT_INCREF            = 0x0201,
    AP_CALLBACK_EVENT_DECREF            = 0x0202,
    AP_CALLBACK_EVENT_NOREF             = 0x0203
} ap_callback_event;

// clang-format on

/**
 * @brief Unified callback signature for allocator-protocol events.
 *
 * The callback derives the protocol from buf (c_ap_protocol_from_ptr) to
 * read the current state (ref_count, size, ...). buf is non-const — the
 * callback may update the buffer in place.
 *
 * @param event      Event type.
 * @param buf        Affected buffer (protocol->buf).
 * @param user_data  Opaque user data pointer passed at registration.
 */
typedef void (*ap_callback_func)(ap_callback_event event, void* buf, void* user_data);

/**
 * @brief Linked-list node for a registered callback.
 */
typedef struct ap_callback_ctx {
    ap_callback_func        fn;         // Callback function pointer.
    void*                   user_data;  // Opaque data from registration.
    uintptr_t               id;         // Opaque ID for unregistration.
    struct ap_callback_ctx* next;       // Next node in linked list.
} ap_callback_ctx;

typedef enum ap_ret_code {
    AP_OK = 0,
    AP_ERR_INVALID_ARG = -1,
    AP_ERR_OOM = -2,
    AP_ERR_NOT_FOUND = -3
} ap_ret_code;

typedef struct allocator_protocol {
    shm_allocator*     shm_allocator;
    shm_allocator_ctx* shm_allocator_ctx;
    heap_allocator*    heap_allocator;
    ap_callback_ctx*   callbacks;
    bool               with_lock;
    bool               with_shm;
    bool               with_freelist;
    size_t             size;
#if AP_ALLOC_VIGILANT > 0
    uint64_t magic;
#endif
    _Atomic int64_t            ref_count;
    struct allocator_protocol* parent;        // Ownership tree — parent block (NULL for roots). NOT refcounted.
    struct allocator_protocol* first_child;   // Head of the owned children list (doubly linked, most recent first).
    struct allocator_protocol* next_sibling;  // Next sibling in the parent's child list.
    struct allocator_protocol* prev_sibling;  // Previous sibling in the parent's child list.
    char                       buf[];
} allocator_protocol;

// ========== Forward Declaration ==========

static inline allocator_protocol* c_ap_allocator_protocol_new(size_t size, shm_allocator_ctx* shm_allocator, heap_allocator* heap_allocator, bool with_lock);
static inline void                c_ap_allocator_protocol_free(allocator_protocol* protocol);
static inline void                c_ap_invoke_callbacks(allocator_protocol* protocol, ap_callback_event event);
static inline bool                c_ap_is_descendant_of(const allocator_protocol* root, const allocator_protocol* node);

static inline allocator_protocol* c_ap_protocol_from_ptr(const void* ptr);
static inline void*               c_ap_parent_of(const void* ptr);
static inline void*               c_ap_alloc(size_t size, allocator_protocol* schematic);
static inline void*               c_ap_alloc_child(size_t size, allocator_protocol* schematic, const void* parent);
static inline void                c_ap_free(void* ptr);
static inline void                c_ap_free_owned(void* ptr);
static inline void                c_ap_incref(const void* ptr);
static inline void                c_ap_decref(const void* ptr);
static inline void                c_ap_acquire_ownership(const void* ptr, const void* parent);
static inline char*               c_ap_strdup(const char* src, allocator_protocol* allocator);
static inline void*               c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator);
static inline bool                c_ap_is_allocator_buf(const void* ptr);

static inline int                 c_ap_register_callback(allocator_protocol* protocol, ap_callback_func callback, void* user_data, uintptr_t* out_id);
static inline int                 c_ap_unregister_callback(allocator_protocol* protocol, uintptr_t callback_id);

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
#if AP_ALLOC_VIGILANT > 0
    // Contract: every allocation path (calloc / heap request / shm request)
    // hands out zeroed memory — the ownership fields must already be NULL.
    if (protocol->parent || protocol->first_child || protocol->next_sibling || protocol->prev_sibling) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: freshly allocated protocol header is not zeroed!\n");
        fflush(stderr);
        abort();
    }
#endif
    // _new method DOES NOT manipulate ref_count! So as the _free method.
    // atomic_store_explicit(&protocol->ref_count, 1, memory_order_release);

#if AP_ALLOC_VIGILANT > 0
    protocol->magic = AP_ALLOC_MAGIC;
#endif

    return protocol;
}

static inline void c_ap_allocator_protocol_free(allocator_protocol* protocol) {
    if (!protocol) return;

    // Free leftover callback nodes (calloc/free — NOT allocator-protocol data).
    ap_callback_ctx* cb = protocol->callbacks;
    while (cb) {
        ap_callback_ctx* next = cb->next;
        free(cb);
        cb = next;
    }

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

static inline void c_ap_invoke_callbacks(allocator_protocol* protocol, ap_callback_event event) {
    if (!protocol || !protocol->callbacks) return;

    ap_callback_ctx* cb = protocol->callbacks;
    while (cb) {
        ap_callback_ctx* next = cb->next;
        if (cb->fn) cb->fn(event, protocol->buf, cb->user_data);
        cb = next;
    }
}

static inline bool c_ap_is_descendant_of(const allocator_protocol* root, const allocator_protocol* node) {
    for (const allocator_protocol* child = root->first_child; child; child = child->next_sibling) {
        if (child == node || c_ap_is_descendant_of(child, node)) return true;
    }
    return false;
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

/**
 * @brief Parent block of an ap-allocated block, or NULL for roots.
 *
 * @param ptr  Block start to inspect (NULL-safe).
 * @return The parent block start (protocol->buf) as void*, or NULL.
 */
static inline void* c_ap_parent_of(const void* ptr) {
    if (!ptr) return NULL;
    allocator_protocol* parent = c_ap_protocol_from_ptr(ptr)->parent;
    return parent ? (void*) parent->buf : NULL;
}

static inline void* c_ap_alloc(size_t size, allocator_protocol* schematic) {
    allocator_protocol* clone;

    if (!schematic) {
        clone = (allocator_protocol*) calloc(1, sizeof(allocator_protocol) + size);
        if (!clone) return NULL;
        clone->size = size;
#if AP_ALLOC_VIGILANT > 0
        // Contract: calloc hands out zeroed memory — the ownership fields
        // must already be NULL.
        if (clone->parent || clone->first_child || clone->next_sibling || clone->prev_sibling) {
            fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: freshly allocated protocol header is not zeroed!\n");
            fflush(stderr);
            abort();
        }
#endif
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
#if AP_ALLOC_VIGILANT > 0
    // Contract: every allocation path (calloc / heap request / shm request)
    // hands out zeroed memory — the ownership fields must already be NULL.
    if (clone->parent || clone->first_child || clone->next_sibling || clone->prev_sibling) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: freshly allocated protocol header is not zeroed!\n");
        fflush(stderr);
        abort();
    }
#endif
    atomic_store_explicit(&clone->ref_count, 1, memory_order_release);
#if AP_ALLOC_VIGILANT > 0
    clone->magic = AP_ALLOC_MAGIC;
#endif
    c_ap_invoke_callbacks(schematic, AP_CALLBACK_EVENT_NEW);
    return (void*) clone->buf;
}

/**
 * @brief Allocate a child block owned by a parent block.
 *
 * Links the new block into the parent's doubly-linked child list (pushed
 * at the head — child order is unspecified). Ownership is structural and
 * NOT refcounted: the parent must outlive the child. Free the tree with
 * c_ap_free_owned; freeing a child individually unlinks it automatically.
 *
 * @param size      Child buffer size in bytes.
 * @param schematic Allocator to allocate with; NULL derives it from the parent.
 * @param parent    Parent buffer (an ap-allocated block start); NULL behaves
 *                  exactly like c_ap_alloc(size, schematic).
 * @return Child buffer pointer, or NULL on invalid parent / OOM.
 */
static inline void* c_ap_alloc_child(size_t size, allocator_protocol* schematic, const void* parent) {
    if (!parent) return c_ap_alloc(size, schematic);
    if (!schematic) schematic = c_ap_protocol_from_ptr(parent);

    allocator_protocol* parent_protocol = c_ap_protocol_from_ptr(parent);
    void*               child_ptr = c_ap_alloc(size, schematic);
    if (!child_ptr) return NULL;

    allocator_protocol* child = c_ap_protocol_from_ptr(child_ptr);
    child->parent = parent_protocol;
    child->next_sibling = parent_protocol->first_child;
    // child->prev_sibling is already NULL (fresh zeroed block).
    if (parent_protocol->first_child) parent_protocol->first_child->prev_sibling = child;
    parent_protocol->first_child = child;
    return child_ptr;
}

static inline void c_ap_free(void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);

    // Lifecycle: FREE only — AP_CALLBACK_EVENT_DEALLOC is preserved but unused.
    c_ap_invoke_callbacks(protocol, AP_CALLBACK_EVENT_FREE);

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

    if (protocol->first_child) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: c_ap_free on a buffer that still owns children! Use c_ap_free_owned to free the ownership tree!\n");
        fflush(stderr);
        abort();
    }
#endif

    // Unlink from the parent's child list (ownership is structural, not refcounted).
    if (protocol->parent) {
        if (protocol->parent->first_child == protocol) protocol->parent->first_child = protocol->next_sibling;
        else if (protocol->prev_sibling) protocol->prev_sibling->next_sibling = protocol->next_sibling;
        if (protocol->next_sibling) protocol->next_sibling->prev_sibling = protocol->prev_sibling;
        protocol->parent = NULL;
    }

    atomic_store_explicit(&protocol->ref_count, 0, memory_order_release);
    c_ap_allocator_protocol_free(protocol);
}

/**
 * @brief Free a buffer together with the whole ownership tree below it.
 *
 * Recursively frees every child (and their descendants) depth-first, then
 * unlinks the buffer from its own parent and frees it. NULL-safe and
 * idempotent-safe on already-freed (invalidated) pointers is NOT
 * guaranteed — pass live ap-allocated buffers only. c_ap_free is the
 * non-recursive counterpart: it refuses (VIGILANT) to free a buffer that
 * still owns children.
 *
 * @param ptr  Buffer to free together with its owned children.
 */
static inline void c_ap_free_owned(void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);

    allocator_protocol* child = protocol->first_child;
    while (child) {
        allocator_protocol* next = child->next_sibling;  // Snapshot — the free below rewires the list.
        c_ap_free_owned(child->buf);
        child = next;
    }

    c_ap_free(ptr);
}

static inline void c_ap_incref(const void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);
    int64_t             ref_count = atomic_fetch_add_explicit(&protocol->ref_count, 1, memory_order_acq_rel) + 1;

#if AP_ALLOC_VIGILANT > 0
    // Adopting a non-owned block (0 -> 1, e.g. a fresh schematic) is legal;
    // only a negative transition (over-decref'd block) aborts.
    if (ref_count < 1) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: incref on over-decref'd allocator protocol (new_ref_count=%lld)!\n", (long long) ref_count);
        fflush(stderr);
        abort();
    }
#endif

    c_ap_invoke_callbacks(protocol, AP_CALLBACK_EVENT_INCREF);
}

static inline void c_ap_decref(const void* ptr) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);
    int64_t             ref_count = atomic_fetch_sub_explicit(&protocol->ref_count, 1, memory_order_acq_rel) - 1;

#if AP_ALLOC_VIGILANT > 0
    if (ref_count < 0) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: decref on unowned allocator protocol (new_ref_count=%lld)!\n", (long long) ref_count);
        fflush(stderr);
        abort();
    }
#endif

    if (ref_count > 0) {
        c_ap_invoke_callbacks(protocol, AP_CALLBACK_EVENT_DECREF);
    }
    else {
        // Reaching 0 emits NOREF; DEALLOC follows if autofree is enabled.
        c_ap_invoke_callbacks(protocol, AP_CALLBACK_EVENT_NOREF);
    }

#if AP_DECREF_AUTOFREE > 0
    if (ref_count == 0) {
        // The last reference dropped — the owned tree dies with the block
        // (c_ap_free_owned takes care of children, which would dangle here).
        c_ap_free_owned(protocol->buf);
    }
#endif
}

/**
 * @brief Acquire ownership of a block — detach it or re-parent it.
 *
 * With parent == NULL the block is unlinked from its current tree and
 * becomes an independent root that owns itself (idempotent on roots).
 * With a parent given, the block — together with its whole subtree — is
 * moved out of its current tree and linked as a child of the new parent
 * (pushed at the head). A block cannot be parented under itself or its
 * own descendant (VIGILANT). The ref_count is NOT touched.
 *
 * @param ptr     Block to acquire (an ap-allocated block start).
 * @param parent  New owner block start, or NULL to detach (self-owned).
 */
static inline void c_ap_acquire_ownership(const void* ptr, const void* parent) {
    if (!ptr) return;
    allocator_protocol* protocol = c_ap_protocol_from_ptr(ptr);
    allocator_protocol* new_parent = parent ? c_ap_protocol_from_ptr(parent) : NULL;

    // Unlink from the current tree.
    if (protocol->parent) {
        if (protocol->parent->first_child == protocol) {
            protocol->parent->first_child = protocol->next_sibling;
        }
        else if (protocol->prev_sibling) {
            protocol->prev_sibling->next_sibling = protocol->next_sibling;
        }
        if (protocol->next_sibling) protocol->next_sibling->prev_sibling = protocol->prev_sibling;
        protocol->parent = NULL;
    }

    if (!new_parent) {
        protocol->prev_sibling = NULL;
        protocol->next_sibling = NULL;
        return;
    }

#if AP_ALLOC_VIGILANT > 0
    if (new_parent == protocol || c_ap_is_descendant_of(protocol, new_parent)) {
        fprintf(stderr, "[AP_ALLOC_VIGILANT] ERROR: c_ap_acquire_ownership cannot parent a block under itself or its own descendant!\n");
        fflush(stderr);
        abort();
    }
#endif

    // Link under the new parent (push-front).
    protocol->next_sibling = new_parent->first_child;
    protocol->prev_sibling = NULL;
    if (new_parent->first_child) new_parent->first_child->prev_sibling = protocol;
    new_parent->first_child = protocol;
    protocol->parent = new_parent;
}

static inline char* c_ap_strdup(const char* src, allocator_protocol* allocator) {
    if (!src) return NULL;
    size_t len = strlen(src);
    char*  trg = (char*) c_ap_alloc(len + 1, allocator);
    if (!trg) return NULL;
    memcpy(trg, src, len);
    return trg;
}

/**
 * @brief Reallocate a buffer — in-place on shrink, alloc-copy-migrate on grow.
 *
 * Shrink (new_size <= size): the allocator cannot recycle the tail of a
 * block, so only the header size is updated in place (same pointer
 * returned) and a warning is logged to stderr — shrinking makes no sense
 * with the allocator protocol.
 *
 * Grow (new_size > size): allocates a fresh block, copies the content, and
 * migrates the hierarchy — children's parent pointers are re-pointed at
 * the new block, and — when the reallocated buffer is itself a child —
 * its parent's child list is patched to reference the new block. The old
 * block is detached and freed. As with c_ap_free, a shared (ref_count>1)
 * buffer aborts under VIGILANT.
 *
 * new_size == 0: ambiguous (plain free vs free_owned) — logs and aborts.
 *
 * @param src       Buffer to reallocate (NULL behaves like c_ap_alloc).
 * @param new_size  New buffer size in bytes (must be > 0).
 * @param allocator Allocator for the grown block (may be NULL).
 * @return The (possibly moved) buffer pointer, or NULL on OOM.
 */
static inline void* c_ap_realloc(void* src, size_t new_size, allocator_protocol* allocator) {
    if (!src) return c_ap_alloc(new_size, allocator);
    if (new_size == 0) {
        fprintf(stderr, "[c_ap_realloc] ERROR: realloc to size 0 is ambiguous (plain free vs free_owned) — aborting!\n");
        fflush(stderr);
        abort();
    }

    allocator_protocol* old = c_ap_protocol_from_ptr(src);

    // Shrink in place: the block is not recycled — only the header size changes.
    if (new_size <= old->size) {
        fprintf(stderr, "[c_ap_realloc] WARNING: shrinking %zu -> %zu only updates the header size; the block is not recycled!\n", old->size, new_size);
        old->size = new_size;
        return src;
    }

    size_t copy_size = old->size;
    void*  new_ptr = c_ap_alloc(new_size, allocator);
    if (!new_ptr) return NULL;
    allocator_protocol* new_proto = c_ap_protocol_from_ptr(new_ptr);
    memcpy(new_ptr, src, copy_size);

    // Migrate the ownership tree onto the moved block.
    new_proto->parent = old->parent;
    new_proto->first_child = old->first_child;
    new_proto->next_sibling = old->next_sibling;
    new_proto->prev_sibling = old->prev_sibling;
    for (allocator_protocol* child = new_proto->first_child; child; child = child->next_sibling) {
        child->parent = new_proto;
    }
    if (new_proto->parent) {
        if (new_proto->parent->first_child == old) {
            new_proto->parent->first_child = new_proto;
        }
        else if (new_proto->prev_sibling) {
            new_proto->prev_sibling->next_sibling = new_proto;
        }
        if (new_proto->next_sibling) new_proto->next_sibling->prev_sibling = new_proto;
    }

    // Detach the old block so c_ap_free sees a lone block.
    old->parent = NULL;
    old->first_child = NULL;
    old->next_sibling = NULL;
    old->prev_sibling = NULL;
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

/**
 * @brief Register a callback on an allocator protocol.
 *
 * Callback nodes are allocated with calloc and freed with free (short-lived
 * registration state — NOT allocator-protocol data). Registrations are
 * process-local: a protocol shared across processes must not be registered
 * by more than one process at a time.
 *
 * @param protocol   Protocol to observe (derive with c_ap_protocol_from_ptr).
 * @param callback   Unified allocator-protocol callback function.
 * @param user_data  Opaque pointer passed to every callback invocation.
 * @param out_id     Receives an opaque ID for unregistration (may be NULL).
 * @return AP_OK on success, AP_ERR_OOM on allocation failure.
 */
static inline int c_ap_register_callback(allocator_protocol* protocol, ap_callback_func callback, void* user_data, uintptr_t* out_id) {
    if (!protocol || !callback) return AP_ERR_INVALID_ARG;

    ap_callback_ctx* node = (ap_callback_ctx*) calloc(1, sizeof(ap_callback_ctx));
    if (!node) return AP_ERR_OOM;

    node->fn = callback;
    node->user_data = user_data;
    node->id = (uintptr_t) node;

    if (!protocol->callbacks) {
        protocol->callbacks = node;
    }
    else {
        ap_callback_ctx* tail = protocol->callbacks;
        while (tail->next) tail = tail->next;
        tail->next = node;
    }

    if (out_id) *out_id = node->id;
    return AP_OK;
}

/**
 * @brief Unregister a previously registered callback by its opaque ID.
 *
 * @param protocol    Protocol the callback was registered on.
 * @param callback_id Opaque ID returned by c_ap_register_callback.
 * @return AP_OK on success, AP_ERR_NOT_FOUND if not registered.
 */
static inline int c_ap_unregister_callback(allocator_protocol* protocol, uintptr_t callback_id) {
    if (!protocol) return AP_ERR_INVALID_ARG;

    ap_callback_ctx* prev = NULL;
    ap_callback_ctx* curr = protocol->callbacks;

    while (curr) {
        if (curr->id == callback_id) {
            if (prev) prev->next = curr->next;
            else protocol->callbacks = curr->next;
            free(curr);
            return AP_OK;
        }
        prev = curr;
        curr = curr->next;
    }

    return AP_ERR_NOT_FOUND;
}

#endif /* C_ALLOCATOR_PROTOCOL_H */