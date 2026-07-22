#ifndef C_CBASE_INTERN_STRING_H
#define C_CBASE_INTERN_STRING_H

/**
 * c_intern_string.h -- Intern string pool.
 *
 * Ported from PyAlgoEngine's algo_engine/base/c_intern_string.h.
 *
 * Two backends, controlled by the ISTR_USE_BYTEMAP_BACKEND macro:
 *
 *   Native (ISTR_USE_BYTEMAP_BACKEND == 0, default):
 *     Original open-addressing hash map with linear probing,
 *     power-of-two capacity, and internal pthread_mutex_t.
 *     istr_entry and istr_map are self-contained structs.
 *     Faithfully ported from PyAlgoEngine -- identical algorithm.
 *
 *   Bytemap-backed (ISTR_USE_BYTEMAP_BACKEND == 1):
 *     istr_entry and istr_map are direct typedefs to bytemap_entry
 *     and bytemap -- zero wrapper overhead, one fewer dereference.
 *     Thread safety is managed at the Cython layer; _synced
 *     variants are pass-through stubs.
 *
 * Each backend defines its own struct layout behind the #if;
 * only forward declarations are shared.  Switch the macro and
 * recompile to compare performance.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include "cbase/nt/pthread_nt_compat.h"
#else
#include <pthread.h>
#endif

#include <cbase/allocator_protocol/c_allocator_protocol.h>

// ========== Configurable Macros ==========

#ifndef ISTR_USE_BYTEMAP_BACKEND
#define ISTR_USE_BYTEMAP_BACKEND 0
#endif

#if ISTR_USE_BYTEMAP_BACKEND
#include <cbase/bytemap/c_bytemap.h>
#endif

#ifndef FNV_OFFSET_BASIS
#define FNV_OFFSET_BASIS 14695981039346656037ULL
#endif

#ifndef FNV_PRIME
#define FNV_PRIME 1099511628211ULL
#endif

#ifndef ISTR_INITIAL_CAPACITY
#define ISTR_INITIAL_CAPACITY 4096
#endif

// ========== Structs (per-backend definitions) ==========

#if !ISTR_USE_BYTEMAP_BACKEND

typedef struct istr_entry {
    const char*        key;
    size_t             key_length;
    uint64_t           hash;
    struct istr_entry* next;
} istr_entry;

typedef struct istr_map {
    pthread_mutex_t lock;
    istr_entry*     table;
    size_t          capacity;
    size_t          size;
    istr_entry*     first;
} istr_map;

#else  // ISTR_USE_BYTEMAP_BACKEND == 1

typedef bytemap_entry istr_entry;

typedef struct istr_map {
    bytemap         base;
    pthread_mutex_t lock;
} istr_map;

#endif  // ISTR_USE_BYTEMAP_BACKEND

typedef enum istr_ret_code {
    ISTR_OK = 0,
    ISTR_ERR_OOM = -1,
    ISTR_ERR_INVALID_BUF = -2,
    ISTR_ERR_INVALID_KEY = -3,
    ISTR_ERR_NOT_FOUND = -4
} istr_ret_code;

// ========== Unified Accessors (abstract field layout differences) ==========

static inline size_t      istr_map_size(const istr_map* map);
static inline istr_entry* istr_map_first(const istr_map* map);
static inline size_t      istr_map_capacity(const istr_map* map);

// ========== Forward Declarations ==========

/*
 * @brief FNV-1a hash function for strings.
 * @param key        Input string.
 * @param key_length Length of the input string.
 * @return 64-bit hash value.
 */
static inline uint64_t fnv1a_hash(const char* key, size_t key_length);

/*
 * @brief Round up n to the next power of two.
 * @param n Input value.
 * @return Smallest power of two >= n, minimum 1.
 */
static inline size_t c_next_pow2(size_t n);

/*
 * @brief Create a new interned string map.
 * @param capacity  Initial capacity of the map (0 for default).
 * @param allocator Allocator protocol instance.
 * @return Pointer to the newly created istr_map, or NULL on failure.
 */
static inline istr_map* c_istr_map_new(size_t capacity, allocator_protocol* allocator);

/*
 * @brief Free an interned string map and all its entries.
 * @param map Pointer to the istr_map to free.
 */
static inline void c_istr_map_free(istr_map* map);

/*
 * @brief Extend the capacity of an interned string map (unlocked).
 * @param map         Pointer to the istr_map to extend.
 * @param new_capacity New capacity (0 to auto double).
 * @return 0 on success, -1 on failure.
 */
static inline int c_istr_map_extend(istr_map* map, size_t new_capacity);

/*
 * @brief Extend the capacity of an interned string map (locked).
 * @param map         Pointer to the istr_map to extend.
 * @param new_capacity New capacity (0 to auto double).
 * @return 0 on success, -1 on failure.
 */
static inline int c_istr_map_extend_synced(istr_map* map, size_t new_capacity);

/*
 * @brief Look up an interned string in the map (unlocked).
 * @param map        Pointer to the istr_map.
 * @param key        Input string to look up.
 * @param key_length Length of key (0 to auto-detect via strlen).
 * @return Pointer to the istr_entry if found, or NULL if not found.
 */
static inline const istr_entry* c_istr_map_lookup(const istr_map* map, const char* key, size_t key_length);

/*
 * @brief Look up an interned string in the map (locked).
 */
static inline const istr_entry* c_istr_map_lookup_synced(const istr_map* map, const char* key, size_t key_length);

/*
 * @brief Intern a string, returning a pointer to the internalized copy (unlocked).
 * @param map        Pointer to the istr_map.
 * @param key        Input string to intern.
 * @param key_length Length of key (0 to auto-detect via strlen).
 * @param out_entry  If non-NULL, receives pointer to the entry.
 * @return Pointer to the interned (owned) string, or NULL on failure.
 */
static inline const char* c_istr(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry);

/*
 * @brief Intern a string, returning a pointer to the internalized copy (locked).
 */
static inline const char* c_istr_synced(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry);

// ========== Common Implementations ==========

static inline uint64_t fnv1a_hash(const char* key, size_t key_length) {
    uint64_t hash = FNV_OFFSET_BASIS;
    for (size_t i = 0; i < key_length; ++i) {
        hash ^= (uint8_t) key[i];
        hash *= FNV_PRIME;
    }
    return hash;
}

static inline size_t c_next_pow2(size_t n) {
    if (n == 0) return 1;
    n--;
    n |= n >> 1;
    n |= n >> 2;
#if __SIZEOF_SIZE_T__ >= 2
    n |= n >> 8;
#endif
#if __SIZEOF_SIZE_T__ >= 4
    n |= n >> 16;
#endif
#if __SIZEOF_SIZE_T__ >= 8
    n |= n >> 32;
#endif
#if __SIZEOF_SIZE_T__ >= 16
    n |= n >> 64;
#endif
    n++;
    return n;
}

// ==================================================================
//  Backend: Native (original PyAlgoEngine, faithfully ported)
// ==================================================================

#if !ISTR_USE_BYTEMAP_BACKEND

// --- unified accessors ---
static inline size_t      istr_map_size(const istr_map* map) { return map->size; }
static inline istr_entry* istr_map_first(const istr_map* map) { return map->first; }
static inline size_t      istr_map_capacity(const istr_map* map) { return map->capacity; }

static inline istr_map*   c_istr_map_new(size_t capacity, allocator_protocol* allocator) {
    capacity = (capacity == 0) ? ISTR_INITIAL_CAPACITY : c_next_pow2(capacity);

    istr_map* map = c_ap_alloc(sizeof(istr_map), allocator);
    if (!map) return NULL;

    istr_entry* table = c_ap_alloc(capacity * sizeof(istr_entry), allocator);
    if (!table) {
        c_ap_free(map);
        return NULL;
    }

    if (pthread_mutex_init(&map->lock, NULL) != 0) {
        c_ap_free(table);
        c_ap_free(map);
        return NULL;
    }

    map->capacity = capacity;
    map->table = table;

    return map;
}

static inline void c_istr_map_free(istr_map* map) {
    if (!map) return;

    // Free interned strings before releasing the pool
    istr_entry* it = map->first;
    while (it) {
        if (it->key) {
            c_ap_free((void*) it->key);
        }
        it = it->next;
    }

    pthread_mutex_destroy(&map->lock);

    c_ap_free((void*) map->table);
    c_ap_free((void*) map);
}

static inline int c_istr_map_extend(istr_map* map, size_t new_capacity) {
    if (!map) return ISTR_ERR_INVALID_BUF;

    // Step 1: Determine new capacity
    if (!new_capacity) {
        if (map->capacity >= SIZE_MAX / 2) return ISTR_ERR_OOM;
        else if (map->capacity == 0) {
            new_capacity = ISTR_INITIAL_CAPACITY;
        }
        else {
            new_capacity = map->capacity * 2;
        }
    }
    else {
        new_capacity = c_next_pow2(new_capacity);
        if (new_capacity <= map->capacity) return ISTR_ERR_INVALID_BUF;
    }

    allocator_protocol* allocator = c_ap_protocol_from_ptr(map);
    istr_entry*         new_table;

    // Step 2: Allocate new pool
    new_table = (istr_entry*) c_ap_alloc(new_capacity * sizeof(istr_entry), allocator);
    if (!new_table) return ISTR_ERR_OOM;

    // Step 3: Rehash existing entries into new pool
    istr_entry* current = map->first;
    map->first = NULL;
    size_t mask = new_capacity - 1;

    while (current) {
        istr_entry* next = current->next;
        uint64_t    idx = current->hash & mask;
        istr_entry* entry = new_table + idx;

        // Linear probing for collision resolution
        // There always should be at least one free slot
        while (entry->key) {
            if (++idx == new_capacity) idx = 0;
            entry = new_table + idx;
        }

        entry->key = current->key;
        entry->key_length = current->key_length;
        entry->hash = current->hash;
        entry->next = map->first;
        map->first = entry;

        current = next;
    }

    // Step 4: Free old pool and update map
    c_ap_free((void*) map->table);

    map->table = new_table;
    map->capacity = new_capacity;
    return ISTR_OK;
}

static inline int c_istr_map_extend_synced(istr_map* map, size_t new_capacity) {
    if (!map) return ISTR_ERR_INVALID_BUF;
    pthread_mutex_t* lock = &map->lock;
    pthread_mutex_lock(lock);
    int result = c_istr_map_extend(map, new_capacity);
    pthread_mutex_unlock(lock);
    return result;
}

static inline const istr_entry* c_istr_map_lookup(const istr_map* map, const char* key, size_t key_length) {
    if (!map || !map->capacity || !key) return NULL;

    // Step 0: Resolve key length
    if (key_length == 0) key_length = strlen(key);

    // Step 1: Compute hash and index
    uint64_t    hash = fnv1a_hash(key, key_length);
    size_t      capacity = map->capacity;
    uint64_t    idx = hash & (capacity - 1);
    istr_entry* table = map->table;
    istr_entry* entry = table + idx;

    // Step 2: Search -- length shortcut + memcmp (no strcmp)
    while (entry->key) {
        if (entry->hash == hash && entry->key_length == key_length && memcmp(entry->key, key, key_length) == 0) {
            return entry;
        }
        if (++idx == capacity) idx = 0;
        entry = table + idx;
    }

    return NULL;
}

static inline const istr_entry* c_istr_map_lookup_synced(const istr_map* map, const char* key, size_t key_length) {
    pthread_mutex_t* lock = (pthread_mutex_t*) &map->lock;
    pthread_mutex_lock(lock);
    const istr_entry* out = c_istr_map_lookup(map, key, key_length);
    pthread_mutex_unlock(lock);
    return out;
}

static inline const char* c_istr(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry) {
    if (!map || !map->capacity || !key) return NULL;

    // Step 0: Resolve key length
    if (key_length == 0) key_length = strlen(key);

    // Step 1: Compute hash
    uint64_t hash = fnv1a_hash(key, key_length);

    // Step 2: Check if key already exists
    size_t      capacity = map->capacity;
    uint64_t    idx = hash & (capacity - 1);
    istr_entry* table = map->table;
    istr_entry* entry = table + idx;

    while (entry->key) {
        if (entry->hash == hash && entry->key_length == key_length && memcmp(entry->key, key, key_length) == 0) {
            if (out_entry) *out_entry = entry;
            return entry->key;
        }
        if (++idx == capacity) idx = 0;
        entry = table + idx;
    }

    // Step 3: Check capacity and extend if necessary
    if (map->size >= capacity / 2) {
        if (c_istr_map_extend(map, 0) != ISTR_OK) return NULL;
        return c_istr(map, key, key_length, out_entry);
    }

    // Step 4: Duplicate key
    char*               interned_copy = NULL;
    size_t              total_size = key_length + 1;
    allocator_protocol* allocator = c_ap_protocol_from_ptr(map);

    interned_copy = (char*) c_ap_alloc(total_size, allocator);
    if (!interned_copy) return NULL;
    memcpy(interned_copy, key, total_size);

    // Step 5: Insert new entry
    entry->key = interned_copy;
    entry->key_length = key_length;
    entry->hash = hash;
    entry->next = map->first;
    map->first = entry;
    map->size += 1;
    if (out_entry) *out_entry = entry;
    return interned_copy;
}

static inline const char* c_istr_synced(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry) {
    pthread_mutex_t* lock = &map->lock;
    pthread_mutex_lock(lock);
    const char* out = c_istr(map, key, key_length, out_entry);
    pthread_mutex_unlock(lock);
    return out;
}

// ==================================================================
//  Backend: Bytemap-backed
//  -- istr_entry = bytemap_entry (direct typedef)
//  -- istr_map wraps bytemap as first field + pthread_mutex_t,
//    so (bytemap*)map == &map->base and _synced variants lock
//    map->lock exactly like the native backend.
// ==================================================================

#else  // ISTR_USE_BYTEMAP_BACKEND == 1

// --- unified accessors ---
static inline size_t      istr_map_size(const istr_map* map) { return map->base.size; }
static inline istr_entry* istr_map_first(const istr_map* map) { return (istr_entry*) map->base.first; }
static inline size_t      istr_map_capacity(const istr_map* map) { return map->base.capacity; }

// Single zero byte used as a placeholder value in bytemap slots.
// Intern strings only use the key; the 1-byte value is irrelevant.
static const char _ISTR_SENTINEL = 0;

// ------------------------------------------------------------------
//  Map lifecycle
// ------------------------------------------------------------------

static inline istr_map* c_istr_map_new(size_t capacity, allocator_protocol* allocator) {
    if (capacity == 0) capacity = ISTR_INITIAL_CAPACITY;

    // Allocate the wrapper struct
    istr_map* map = c_ap_alloc(sizeof(istr_map), allocator);
    if (!map) return NULL;

    // Initialize the embedded bytemap in-place
    int ret = c_bytemap_ex_init(&map->base, capacity, 1, allocator);
    if (ret != BYTEMAP_OK) {
        c_ap_free(map);
        return NULL;
    }

    if (pthread_mutex_init(&map->lock, NULL) != 0) {
        c_bytemap_ex_dealloc(&map->base);
        c_ap_free(map);
        return NULL;
    }

    return map;
}

static inline void c_istr_map_free(istr_map* map) {
    if (!map) return;

    c_bytemap_ex_dealloc(&map->base);
    pthread_mutex_destroy(&map->lock);
    c_ap_free(map);
}

// ------------------------------------------------------------------
//  Extend (mirrors native: determine capacity -> rehash, with lock)
// ------------------------------------------------------------------

static inline int c_istr_map_extend(istr_map* map, size_t new_capacity) {
    if (!map) return ISTR_ERR_INVALID_BUF;

    // Step 1: Determine new capacity (identical logic to native backend)
    if (!new_capacity) {
        if (map->base.capacity >= SIZE_MAX / 2) return ISTR_ERR_OOM;
        else if (map->base.capacity == 0) {
            new_capacity = ISTR_INITIAL_CAPACITY;
        }
        else {
            new_capacity = map->base.capacity * 2;
        }
    }
    else {
        new_capacity = c_next_pow2(new_capacity);
        if (new_capacity <= map->base.capacity) return ISTR_ERR_INVALID_BUF;
    }

    // Step 2: Rehash the underlying bytemap
    int ret = c_bytemap_ex_rehash(&map->base, new_capacity, 0);
    if (ret == BYTEMAP_ERR_OOM) return ISTR_ERR_OOM;
    if (ret != BYTEMAP_OK) return ISTR_ERR_INVALID_BUF;
    return ISTR_OK;
}

static inline int c_istr_map_extend_synced(istr_map* map, size_t new_capacity) {
    if (!map) return ISTR_ERR_INVALID_BUF;

    // Temporarily enable allocator-level locking so that c_ap_alloc /
    // c_ap_free calls inside c_bytemap_ex_rehash are also threadsafe.
    allocator_protocol* ap = c_ap_protocol_from_ptr(map);
    bool                saved_lock = ap->with_lock;
    ap->with_lock = true;

    pthread_mutex_lock(&map->lock);
    int result = c_istr_map_extend(map, new_capacity);
    pthread_mutex_unlock(&map->lock);

    ap->with_lock = saved_lock;
    return result;
}

// ------------------------------------------------------------------
//  Lookup -- single linear probe, same structure as native.
//  Uses bytemap's table layout and XXH3 hash (with per-map salt).
// ------------------------------------------------------------------

static inline const istr_entry* c_istr_map_lookup(const istr_map* map, const char* key, size_t key_length) {
    if (!map || !map->base.capacity || !key) return NULL;

    // Step 0: Resolve key length
    if (key_length == 0) key_length = strlen(key);

    // Step 1: Compute hash (bytemap uses XXH3 with per-map salt)
    uint64_t hash;
    c_bytemap_hash(&map->base, key, key_length, &hash);

    // Step 2: Index into the open-addressing table
    size_t      capacity = map->base.capacity;
    size_t      idx = hash % capacity;
    size_t      start = idx;
    istr_entry* entry = c_bytemap_entry_at(&map->base, idx);

    // Step 3: Linear probe -- length shortcut + memcmp
    while (entry->occupied || entry->removed) {
        if (entry->occupied && entry->key_length == key_length && memcmp(entry->key, key, key_length) == 0) {
            return entry;
        }
        idx = (idx + 1) % capacity;
        if (idx == start) break;
        entry = c_bytemap_entry_next(&map->base, entry);
    }

    return NULL;
}

static inline const istr_entry* c_istr_map_lookup_synced(const istr_map* map, const char* key, size_t key_length) {
    if (!map) return NULL;
    pthread_mutex_lock((pthread_mutex_t*) &map->lock);
    const istr_entry* out = c_istr_map_lookup(map, key, key_length);
    pthread_mutex_unlock((pthread_mutex_t*) &map->lock);
    return out;
}

// ------------------------------------------------------------------
//  Intern -- delegates to c_bytemap_ex_set which handles hash,
//  linear probe, auto-rehash, key cloning, and insertion order.
// ------------------------------------------------------------------

static inline const char* c_istr(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry) {
    if (!map || !map->base.capacity || !key) return NULL;

    // Step 0: Resolve key length
    if (key_length == 0) key_length = strlen(key);
    if (key_length == 0) return NULL;

    // Step 1: Insert or retrieve via bytemap.
    istr_entry* entry = NULL;
    int         ret = c_bytemap_ex_set(
        &map->base, key, key_length,
        &_ISTR_SENTINEL, 1,  // 1-byte sentinel value
        0,                   // seq_id (no callbacks)
        &entry
    );
    if (ret != BYTEMAP_OK) return NULL;

    // Step 2: Return results
    if (out_entry) *out_entry = entry;
    return entry->key;
}

static inline const char* c_istr_synced(istr_map* map, const char* key, size_t key_length, const istr_entry** out_entry) {
    if (!map) return NULL;

    // Temporarily enable allocator-level locking so that any c_ap_alloc
    // calls inside c_bytemap_ex_set (key cloning, rehash) are also threadsafe.
    allocator_protocol* ap = c_ap_protocol_from_ptr(map);
    bool                saved_lock = ap->with_lock;
    ap->with_lock = true;

    pthread_mutex_lock(&map->lock);
    const char* out = c_istr(map, key, key_length, out_entry);
    pthread_mutex_unlock(&map->lock);

    ap->with_lock = saved_lock;
    return out;
}

#endif  // ISTR_USE_BYTEMAP_BACKEND

#endif  // C_CBASE_INTERN_STRING_H
