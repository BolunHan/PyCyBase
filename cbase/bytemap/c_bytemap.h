#ifndef C_BYTEMAP_H
#define C_BYTEMAP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <cbase/allocator_protocol/c_allocator_protocol.h>
#include <cbase/bytemap/xxh3.h>

// ========== Constants ==========

#ifndef MIN_BYTEMAP_CAPACITY
#define MIN_BYTEMAP_CAPACITY 16U
#endif

#ifndef DEFAULT_BYTEMAP_CAPACITY
#define DEFAULT_BYTEMAP_CAPACITY 64U
#endif

#ifndef BYTEMAP_GROWTH_FACTOR
#define BYTEMAP_GROWTH_FACTOR 2U
#endif

#if BYTEMAP_GROWTH_FACTOR < 2U
#error "BYTEMAP_GROWTH_FACTOR must be >= 2"
#endif

#ifndef MAX_BYTEMAP_CAPACITY
#define MAX_BYTEMAP_CAPACITY ((size_t) (SIZE_MAX / sizeof(bytemap_entry) / BYTEMAP_GROWTH_FACTOR))
#endif

#ifndef BYTEMAP_SALT_MAGIC
#define BYTEMAP_SALT_MAGIC 0x9E3779B97F4A7C15ULL
#endif

// ========== Structs ==========

// clang-format off

/**
 * @brief A single open-addressing table slot with inline value storage.
 *
 * The value is stored as raw bytes in the flexible array member `value[]`.
 * The actual entry size on the table is `sizeof(bytemap_entry) + slot_capacity`.
 */
typedef struct bytemap_entry {
    uint64_t              hash;          // Cached hash of key for faster probing/rehash.
    size_t                key_length;    // Length of key (excludes NUL).
    const char*           key;           // Cloned key bytes (owned by the map, NUL-terminated).
    size_t                value_length;  // Length of value stored in `value[]`.
    bool                  occupied;      // true if slot holds a live entry.
    bool                  removed;       // true if slot is a tombstone (keeps probe chains intact).
    struct bytemap_entry* prev;          // Previous entry in insertion-order list.
    struct bytemap_entry* next;          // Next entry in insertion-order list.
    char                  value[];       // Inline value storage (flexible array member).
} bytemap_entry;

// bytemap_entry_ex is an alias for the unified entry type.
typedef bytemap_entry bytemap_entry_ex;

typedef enum bytemap_callback_event {
    BYTEMAP_CALLBACK_EVENT_MODIFIED = 0,
    BYTEMAP_CALLBACK_EVENT_ADDED    = 1,
    BYTEMAP_CALLBACK_EVENT_POPPED   = 2,
    BYTEMAP_CALLBACK_EVENT_CLEARED  = 3,
    BYTEMAP_CALLBACK_EVENT_REHASH   = 4,
    BYTEMAP_CALLBACK_EVENT_FREED    = 5
} bytemap_callback_event;

/**
 * @brief Unified callback signature for both bytemap and bytemap_ex.
 *
 * @param event      Mutation event type.
 * @param key        Key involved (NULL for clear/rehash/freed events).
 * @param key_len    Length of key.
 * @param value      Pointer to raw value bytes (NULL for pop/clear/rehash/freed).
 * @param value_len  Length of value bytes.
 * @param seq_id     Sequence ID of the caller (for self-suppression in bound views).
 * @param user_data  Opaque user data pointer passed at registration.
 */
typedef void (*bytemap_callback_func)(bytemap_callback_event event, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, void* user_data);

// Legacy alias — single unified callback type.
typedef bytemap_callback_func bytemap_ex_callback_func;

typedef struct bytemap_callback_ctx {
    bytemap_callback_func        fn;
    void*                        user_data;
    uintptr_t                    id;
    struct bytemap_callback_ctx* next;
} bytemap_callback_ctx;

// Legacy alias — single unified callback context.
typedef bytemap_callback_ctx bytemap_ex_callback_ctx;

/**
 * @brief String-keyed hash map with open addressing, tombstones, and inline value storage.
 *
 * This is the unified map struct.  bytemap_ex is a typedef alias.
 * For the traditional void* variant (bytemap), slot_capacity == sizeof(void*)
 * and the value bytes are read/written as a pointer.
 */
typedef struct bytemap {
    bytemap_entry*        table;          // Backing array of slots.
    bytemap_entry*        first;          // Head of insertion-order doubly linked list.
    bytemap_entry*        last;           // Tail of insertion-order doubly linked list.
    bytemap_callback_ctx* callbacks;      // Optional linked list of mutation callbacks.
    size_t                capacity;       // Number of slots in `table`.
    size_t                size;           // Number of live entries.
    size_t                occupied;       // Used-slot count since last rehash (live + tombstones).
    uint64_t              salt;           // Per-map hash salt for XXH3.
    size_t                slot_capacity;  // Size of the value slot for each entry (fixed for all entries).
    size_t                entry_size;     // sizeof(bytemap_entry) + slot_capacity.
    void*                 table_end;      // Pointer to the end of the allocated table for bounds checking.
} bytemap;

// bytemap_ex is an alias for the same unified struct.
typedef bytemap bytemap_ex;

typedef enum bytemap_ret_code {
    BYTEMAP_OK                  = 0,
    BYTEMAP_ERR_INVALID_BUF     = -1,
    BYTEMAP_ERR_INVALID_KEY     = -2,
    BYTEMAP_ERR_INVALID_VALUE   = -3,
    BYTEMAP_ERR_NOT_FOUND       = -4,
    BYTEMAP_ERR_FULL            = -5,
    BYTEMAP_ERR_EMPTY           = -6,
    BYTEMAP_ERR_OOM             = -7
} bytemap_ret_code;

// clang-format on

// ========== Forward Declaration ==========

static inline int            c_bytemap_hash(const bytemap* map, const char* key, size_t key_len, uint64_t* out);
static inline const char*    c_bytemap_clone_key(const bytemap* map, const char* key, size_t key_len);
static inline void           c_bytemap_free_key(const bytemap* map, char* key);
static inline uint64_t       c_bytemap_gen_seq_id(const void* ptr);
static inline bytemap_entry* c_bytemap_entry_at(const bytemap* map, size_t idx);
static inline bytemap_entry* c_bytemap_entry_next(const bytemap* map, bytemap_entry* entry);
static inline bytemap_entry* c_bytemap_entry_first(const bytemap* map);
static inline void           c_bytemap_invoke_callbacks(bytemap_callback_event event, const bytemap* map, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id);

static inline bytemap*       c_bytemap_ex_new(size_t capacity, size_t slot_capacity, allocator_protocol* allocator);
static inline void           c_bytemap_ex_clear(bytemap* map);
static inline void           c_bytemap_ex_free(bytemap* map);
static inline int            c_bytemap_ex_register_callback(bytemap* map, bytemap_callback_func callback, void* user_data, uintptr_t* out_id);
static inline int            c_bytemap_ex_unregister_callback(bytemap* map, uintptr_t callback_id);
static inline int            c_bytemap_ex_get(const bytemap* map, const char* key, size_t key_len, char* out, size_t* out_len);
static inline int            c_bytemap_ex_get_ptr(const bytemap* map, const char* key, size_t key_len, char** out, size_t* out_len);
static inline int            c_bytemap_ex_contains(const bytemap* map, const char* key, size_t key_len);
static inline int            c_bytemap_ex_rehash(bytemap* map, size_t new_capacity, uint64_t seq_id);
static inline int            c_bytemap_ex_set(bytemap* map, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, bytemap_entry** out);
static inline int            c_bytemap_ex_pop(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, char* out, size_t* out_len);
static inline int            c_bytemap_ex_pop_ptr(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, char** out, size_t* out_len);
static inline size_t         c_bytemap_ex_len(const bytemap* map);
static inline bytemap*       c_bytemap_ex_clone(const bytemap* src, allocator_protocol* allocator);

static inline int            c_bytemap_ex_set_double(bytemap* map, const char* key, size_t key_len, double value, uint64_t seq_id);
static inline int            c_bytemap_ex_get_double(const bytemap* map, const char* key, size_t key_len, double* out);
static inline int            c_bytemap_ex_pop_double(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, double* out);

static inline bytemap*       c_bytemap_new(size_t capacity, allocator_protocol* allocator);
static inline void           c_bytemap_clear(bytemap* map);
static inline void           c_bytemap_free(bytemap* map);
static inline int            c_bytemap_register_callback(bytemap* map, bytemap_callback_func callback, void* user_data, uintptr_t* out_id);
static inline int            c_bytemap_unregister_callback(bytemap* map, uintptr_t callback_id);
static inline int            c_bytemap_get(const bytemap* map, const char* key, size_t key_len, void** out);
static inline int            c_bytemap_contains(const bytemap* map, const char* key, size_t key_len);
static inline int            c_bytemap_rehash(bytemap* map, size_t new_capacity);
static inline int            c_bytemap_set(bytemap* map, const char* key, size_t key_len, void* value, bytemap_entry** out);
static inline int            c_bytemap_pop(bytemap* map, const char* key, size_t key_len, void** out);
static inline size_t         c_bytemap_len(const bytemap* map);
static inline bytemap*       c_bytemap_clone(const bytemap* src, allocator_protocol* allocator);
static inline bytemap_entry* c_bytemap_first(const bytemap* map);
static inline bytemap_entry* c_bytemap_last(const bytemap* map);
static inline bytemap_entry* c_bytemap_next(const bytemap_entry* entry);
static inline bytemap_entry* c_bytemap_prev(const bytemap_entry* entry);
static inline void*          c_bytemap_entry_value(const bytemap_entry* entry);

// ========== Utility Functions ==========

/**
 * @brief Compute the hash of a key string for the given map.
 */
static inline int c_bytemap_hash(const bytemap* map, const char* key, size_t key_len, uint64_t* out) {
    if (!key) return BYTEMAP_ERR_INVALID_KEY;
    if (!key_len) key_len = strlen(key);
    if (!key_len) return BYTEMAP_ERR_INVALID_KEY;
    *out = map && map->salt ? XXH3_64bits_withSeed(key, key_len, map->salt) : XXH3_64bits(key, key_len);
    return BYTEMAP_OK;
}

/**
 * @brief Clone a key string for storage in the map.
 */
static inline const char* c_bytemap_clone_key(const bytemap* map, const char* key, size_t key_len) {
    if (!map || !key) return NULL;
    if (!key_len) key_len = strlen(key);
    if (!key_len) return NULL;
    allocator_protocol* allocator = c_ap_protocol_from_ptr((void*) map);
    char*               buf = (char*) c_ap_alloc(key_len + 1, allocator);
    if (!buf) return NULL;
    memcpy(buf, key, key_len);
    return buf;
}

/**
 * @brief Free a cloned key string.
 */
static inline void c_bytemap_free_key(const bytemap* map, char* key) {
    (void) map;
    c_ap_free((void*) key);
}

/**
 * @brief Generate a unique seq_id bound to (pointer address, PID).
 *
 * Mixing the PID ensures that in multiprocessing scenarios with shared
 * memory (AP_SHARED), different processes operating on the same bytemap
 * get distinct seq_ids, so cross-process callback suppression works correctly.
 *
 * @param ptr  Opaque pointer (typically the owning Python object).
 * @return     A seq_id suitable for callback self-suppression.
 */
static inline uint64_t c_bytemap_gen_seq_id(const void* ptr) {
    uint64_t addr = (uint64_t) (uintptr_t) ptr;
    uint64_t pid = (uint64_t) getpid();
    return XXH3_64bits_withSeed(&addr, sizeof(addr), pid);
}

// ========== Entry Access Helpers ==========

/**
 * @brief Get a pointer to the entry at a given index in the table.
 */
static inline bytemap_entry* c_bytemap_entry_at(const bytemap* map, size_t idx) {
    return (bytemap_entry*) (((char*) map->table) + (idx * map->entry_size));
}

/**
 * @brief Get the next entry in the table (wraps around at table_end).
 */
static inline bytemap_entry* c_bytemap_entry_next(const bytemap* map, bytemap_entry* entry) {
    void* next_addr = (void*) ((char*) entry + map->entry_size);
    if (next_addr >= map->table_end) return map->table;
    return (bytemap_entry*) next_addr;
}

/**
 * @brief Get the first live entry in insertion order.
 */
static inline bytemap_entry* c_bytemap_entry_first(const bytemap* map) {
    return map ? map->first : NULL;
}

// ========== Callback Helpers ==========

/**
 * @brief Invoke registered callbacks for a mutation event (unified signature).
 */
static inline void c_bytemap_invoke_callbacks(bytemap_callback_event event, const bytemap* map, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id) {
    if (!map || !map->callbacks) return;

    bytemap_callback_ctx* cb = map->callbacks;
    while (cb) {
        bytemap_callback_ctx* next = cb->next;
        if (cb->fn) cb->fn(event, key, key_len, value, value_len, seq_id, cb->user_data);
        cb = next;
    }
}

// ========== Core bytemap_ex APIs (primary implementations) ==========

static inline bytemap* c_bytemap_ex_new(size_t capacity, size_t slot_capacity, allocator_protocol* allocator) {
    if (capacity == 0) capacity = DEFAULT_BYTEMAP_CAPACITY;
    if (capacity < MIN_BYTEMAP_CAPACITY) capacity = MIN_BYTEMAP_CAPACITY;
    if (capacity > MAX_BYTEMAP_CAPACITY) return NULL;
    if (slot_capacity == 0) return NULL;

    size_t   entry_size = sizeof(bytemap_entry) + slot_capacity;
    bytemap* map = (bytemap*) c_ap_alloc(sizeof(bytemap), allocator);
    if (!map) return NULL;
    bytemap_entry* table = (bytemap_entry*) c_ap_alloc(capacity * entry_size, allocator);
    if (!table) {
        c_ap_free((void*) map);
        return NULL;
    }

    map->table = table;
    map->table_end = (void*) ((char*) table + (capacity * entry_size));
    map->capacity = capacity;
    map->slot_capacity = slot_capacity;
    map->entry_size = entry_size;
    uint64_t seed = (uint64_t) (uintptr_t) map ^ (uint64_t) capacity;
    map->salt = XXH3_64bits(&seed, sizeof(seed)) ^ BYTEMAP_SALT_MAGIC;
    return map;
}

static inline void c_bytemap_ex_clear(bytemap* map) {
    if (!map || !map->table) return;

    bytemap_entry* e = map->table;
    size_t         entry_size = map->entry_size;

    for (size_t i = 0; i < map->capacity; ++i) {
        if (e->occupied) c_bytemap_free_key(map, (char*) e->key);
        memset(e, 0, entry_size);
        e = c_bytemap_entry_next(map, e);
    }

    map->first = map->last = NULL;
    map->size = 0;
    map->occupied = 0;
    c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_CLEARED, map, NULL, 0, NULL, 0, (uint64_t) -1);
}

static inline void c_bytemap_ex_free(bytemap* map) {
    if (!map) return;

    c_bytemap_ex_clear(map);
    c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_FREED, map, NULL, 0, NULL, 0, (uint64_t) -1);

    bytemap_callback_ctx* cb = map->callbacks;
    while (cb) {
        bytemap_callback_ctx* next = cb->next;
        free(cb);
        cb = next;
    }

    if (map->table) c_ap_free(map->table);

    c_ap_free(map);
}

static inline int c_bytemap_ex_register_callback(bytemap* map, bytemap_callback_func callback, void* user_data, uintptr_t* out_id) {
    if (!map || !callback) return BYTEMAP_ERR_INVALID_BUF;

    bytemap_callback_ctx* node = (bytemap_callback_ctx*) calloc(1, sizeof(bytemap_callback_ctx));
    if (!node) return BYTEMAP_ERR_OOM;

    node->fn = callback;
    node->user_data = user_data;
    node->id = (uintptr_t) node;

    if (!map->callbacks) {
        map->callbacks = node;
    }
    else {
        bytemap_callback_ctx* tail = map->callbacks;
        while (tail->next) tail = tail->next;
        tail->next = node;
    }

    if (out_id) *out_id = node->id;
    return BYTEMAP_OK;
}

static inline int c_bytemap_ex_unregister_callback(bytemap* map, uintptr_t callback_id) {
    if (!map) return BYTEMAP_ERR_INVALID_BUF;

    bytemap_callback_ctx* prev = NULL;
    bytemap_callback_ctx* curr = map->callbacks;

    while (curr) {
        if (curr->id == callback_id) {
            if (prev) prev->next = curr->next;
            else map->callbacks = curr->next;
            free(curr);
            return BYTEMAP_OK;
        }
        prev = curr;
        curr = curr->next;
    }

    return BYTEMAP_ERR_NOT_FOUND;
}

static inline int c_bytemap_ex_get(const bytemap* map, const char* key, size_t key_len, char* out, size_t* out_len) {
    if (!map || !map->table || !key) return BYTEMAP_ERR_INVALID_BUF;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t         idx = hash % map->capacity;
    size_t         start = idx;
    bytemap_entry* entry = c_bytemap_entry_at(map, idx);

    while (entry->occupied || entry->removed) {
        if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0) {
            if (out) memcpy(out, entry->value, entry->value_length);
            if (out_len) *out_len = entry->value_length;
            return BYTEMAP_OK;
        }
        idx = (idx + 1) % map->capacity;
        entry = c_bytemap_entry_next(map, entry);
        if (idx == start) break;
    }
    return BYTEMAP_ERR_NOT_FOUND;
}

static inline int c_bytemap_ex_get_ptr(const bytemap* map, const char* key, size_t key_len, char** out, size_t* out_len) {
    if (!map || !map->table || !key) return BYTEMAP_ERR_INVALID_BUF;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t         idx = hash % map->capacity;
    size_t         start = idx;
    bytemap_entry* entry = c_bytemap_entry_at(map, idx);

    while (entry->occupied || entry->removed) {
        if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0) {
            if (out) *out = entry->value;
            if (out_len) *out_len = entry->value_length;
            return BYTEMAP_OK;
        }
        idx = (idx + 1) % map->capacity;
        entry = c_bytemap_entry_next(map, entry);
        if (idx == start) break;
    }
    return BYTEMAP_ERR_NOT_FOUND;
}

static inline int c_bytemap_ex_contains(const bytemap* map, const char* key, size_t key_len) {
    if (!map || !map->table || !key) return BYTEMAP_ERR_INVALID_BUF;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t         idx = hash % map->capacity;
    size_t         start = idx;
    bytemap_entry* entry = c_bytemap_entry_at(map, idx);

    while (entry->occupied || entry->removed) {
        if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0)
            return BYTEMAP_OK;
        idx = (idx + 1) % map->capacity;
        entry = c_bytemap_entry_next(map, entry);
        if (idx == start) break;
    }
    return BYTEMAP_ERR_NOT_FOUND;
}

static inline int c_bytemap_ex_rehash(bytemap* map, size_t new_capacity, uint64_t seq_id) {
    if (!map || new_capacity == 0 || new_capacity > MAX_BYTEMAP_CAPACITY) return BYTEMAP_ERR_INVALID_BUF;

    allocator_protocol* allocator = c_ap_protocol_from_ptr((void*) map);
    size_t              entry_size = map->entry_size;
    bytemap_entry*      new_table = (bytemap_entry*) c_ap_alloc(new_capacity * entry_size, allocator);
    if (!new_table) return BYTEMAP_ERR_OOM;

    bytemap_entry* new_first = NULL;
    bytemap_entry* new_last = NULL;

    for (bytemap_entry* e = map->first; e; e = e->next) {
        size_t         idx = e->hash % new_capacity;
        bytemap_entry* entry = (bytemap_entry*) (((char*) new_table) + (idx * entry_size));
        while (entry->occupied) {
            idx = (idx + 1) % new_capacity;
            entry = (bytemap_entry*) (((char*) new_table) + (idx * entry_size));
        }
        memcpy(entry, e, entry_size);
        entry->prev = new_last;
        entry->next = NULL;
        if (new_last) new_last->next = entry;
        else new_first = entry;
        new_last = entry;
    }

    c_ap_free(map->table);
    map->table = new_table;
    map->table_end = (void*) ((char*) new_table + (new_capacity * entry_size));
    map->capacity = new_capacity;
    map->occupied = map->size;
    map->first = new_first;
    map->last = new_last;
    c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_REHASH, map, NULL, 0, NULL, 0, seq_id);
    return BYTEMAP_OK;
}

static inline int c_bytemap_ex_set(bytemap* map, const char* key, size_t key_len, const char* value, size_t value_len, uint64_t seq_id, bytemap_entry** out) {
    if (!map) return BYTEMAP_ERR_INVALID_BUF;
    if (!key) return BYTEMAP_ERR_INVALID_KEY;
    if (!value || value_len > map->slot_capacity) return BYTEMAP_ERR_INVALID_VALUE;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

probe:
    size_t   capacity = map->capacity;
    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t         idx = hash % capacity;
    size_t         start = idx;
    bytemap_entry* tombstone = NULL;
    bytemap_entry* entry = c_bytemap_entry_at(map, idx);

    while (entry->occupied || entry->removed) {
        if (!entry->occupied && !tombstone) tombstone = entry;
        else if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0) {
            memcpy(entry->value, value, value_len);
            entry->value_length = value_len;
            if (out) *out = entry;
            c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_MODIFIED, map, entry->key, key_len, entry->value, value_len, seq_id);
            return BYTEMAP_OK;
        }
        idx = (idx + 1) % capacity;
        entry = c_bytemap_entry_next(map, entry);
        if (idx == start) {
            if (tombstone) {
                entry = tombstone;
                break;
            }

            size_t new_cap;
            if (capacity == 0) new_cap = MIN_BYTEMAP_CAPACITY;
            else if (capacity > MAX_BYTEMAP_CAPACITY / BYTEMAP_GROWTH_FACTOR) new_cap = MAX_BYTEMAP_CAPACITY;
            else new_cap = capacity * BYTEMAP_GROWTH_FACTOR;
            if (new_cap == capacity) return BYTEMAP_ERR_FULL;
            int ret_code = c_bytemap_ex_rehash(map, new_cap, seq_id);
            if (ret_code != BYTEMAP_OK) return ret_code;
            goto probe;
        }
    }

    if (tombstone) entry = tombstone;
    else {
        if (map->occupied * 2 >= capacity) {
            size_t new_cap;
            if (capacity == 0) new_cap = MIN_BYTEMAP_CAPACITY;
            else if (capacity > MAX_BYTEMAP_CAPACITY / BYTEMAP_GROWTH_FACTOR) new_cap = MAX_BYTEMAP_CAPACITY;
            else new_cap = capacity * BYTEMAP_GROWTH_FACTOR;

            if (new_cap != capacity) {
                int ret_code = c_bytemap_ex_rehash(map, new_cap, seq_id);
                if (ret_code != BYTEMAP_OK) return ret_code;
                goto probe;
            }
        }

        map->occupied++;
    }

    const char* key_copy = c_bytemap_clone_key(map, key, key_len);
    if (!key_copy) return BYTEMAP_ERR_OOM;

    entry->key = key_copy;
    entry->key_length = key_len;
    memcpy(entry->value, value, value_len);
    entry->value_length = value_len;
    entry->hash = hash;
    entry->occupied = true;
    entry->removed = false;

    entry->prev = map->last;
    entry->next = NULL;
    if (map->last) map->last->next = entry;
    else map->first = entry;
    map->last = entry;
    map->size++;
    if (out) *out = entry;
    c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_ADDED, map, entry->key, key_len, entry->value, value_len, seq_id);
    return BYTEMAP_OK;
}

static inline int c_bytemap_ex_pop(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, char* out, size_t* out_len) {
    if (!map || !key) return BYTEMAP_ERR_INVALID_BUF;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

    size_t   entry_size = map->entry_size;
    size_t   capacity = map->capacity;
    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t idx = hash % capacity;
    size_t start = idx;

    while (1) {
        bytemap_entry* entry = c_bytemap_entry_at(map, idx);
        if (!entry->occupied && !entry->removed) break;
        if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0) {
            if (out) memcpy(out, entry->value, entry->value_length);
            if (out_len) *out_len = entry->value_length;

            if (entry->prev) entry->prev->next = entry->next;
            else map->first = entry->next;
            if (entry->next) entry->next->prev = entry->prev;
            else map->last = entry->prev;

            c_bytemap_free_key(map, (char*) entry->key);
            memset(entry, 0, entry_size);
            entry->removed = 1;
            map->size--;
            c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_POPPED, map, key, key_len, NULL, 0, seq_id);
            return BYTEMAP_OK;
        }
        idx = (idx + 1) % capacity;
        if (idx == start) break;
    }
    return BYTEMAP_ERR_NOT_FOUND;
}

static inline int c_bytemap_ex_pop_ptr(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, char** out, size_t* out_len) {
    if (!map || !key) return BYTEMAP_ERR_INVALID_BUF;
    if (key_len == 0) key_len = strlen(key);
    if (key_len == 0) return BYTEMAP_ERR_INVALID_KEY;

    size_t   entry_size = map->entry_size;
    size_t   capacity = map->capacity;
    uint64_t hash;
    c_bytemap_hash(map, key, key_len, &hash);
    size_t idx = hash % capacity;
    size_t start = idx;

    while (1) {
        bytemap_entry* entry = c_bytemap_entry_at(map, idx);
        if (!entry->occupied && !entry->removed) break;
        if (entry->occupied && entry->key_length == key_len && memcmp(entry->key, key, key_len) == 0) {
            if (out) *out = entry->value;
            if (out_len) *out_len = entry->value_length;

            if (entry->prev) entry->prev->next = entry->next;
            else map->first = entry->next;
            if (entry->next) entry->next->prev = entry->prev;
            else map->last = entry->prev;

            c_bytemap_free_key(map, (char*) entry->key);
            memset(entry, 0, entry_size);
            entry->removed = 1;
            map->size--;
            c_bytemap_invoke_callbacks(BYTEMAP_CALLBACK_EVENT_POPPED, map, key, key_len, NULL, 0, seq_id);
            return BYTEMAP_OK;
        }
        idx = (idx + 1) % capacity;
        if (idx == start) break;
    }
    return BYTEMAP_ERR_NOT_FOUND;
}

static inline size_t c_bytemap_ex_len(const bytemap* map) {
    return map ? map->size : 0;
}

static inline bytemap* c_bytemap_ex_clone(const bytemap* src, allocator_protocol* allocator) {
    if (!src) return NULL;

    bytemap* dst = c_bytemap_ex_new(src->capacity, src->slot_capacity, allocator);
    if (!dst) return NULL;

    dst->salt = src->salt;

    for (bytemap_entry* e = src->first; e; e = e->next) {
        if (!e->occupied) continue;
        int ret = c_bytemap_ex_set(dst, e->key, e->key_length, e->value, e->value_length, 0, NULL);
        if (ret != BYTEMAP_OK) {
            c_bytemap_ex_free(dst);
            return NULL;
        }
    }

    return dst;
}

// ========== Predefined typed helpers (double) ==========

static inline int c_bytemap_ex_set_double(bytemap* map, const char* key, size_t key_len, double value, uint64_t seq_id) {
    return c_bytemap_ex_set(map, key, key_len, (const char*) &value, sizeof(double), seq_id, NULL);
}

static inline int c_bytemap_ex_get_double(const bytemap* map, const char* key, size_t key_len, double* out) {
    return c_bytemap_ex_get(map, key, key_len, (char*) out, NULL);
}

static inline int c_bytemap_ex_pop_double(bytemap* map, const char* key, size_t key_len, uint64_t seq_id, double* out) {
    return c_bytemap_ex_pop(map, key, key_len, seq_id, (char*) out, NULL);
}

// ========== bytemap void* convenience wrappers ==========
// These call the bytemap_ex (primary) functions with slot_capacity=sizeof(void*)
// and perform void* <-> raw bytes conversion.

/**
 * @brief Create a new bytemap (void* variant).
 *        Equivalent to c_bytemap_ex_new(capacity, sizeof(void*), allocator).
 */
static inline bytemap* c_bytemap_new(size_t capacity, allocator_protocol* allocator) {
    return c_bytemap_ex_new(capacity, sizeof(void*), allocator);
}

/**
 * @brief Clear all entries from a bytemap (void* variant).
 */
static inline void c_bytemap_clear(bytemap* map) {
    c_bytemap_ex_clear(map);
}

/**
 * @brief Free a bytemap (void* variant).
 */
static inline void c_bytemap_free(bytemap* map) {
    c_bytemap_ex_free(map);
}

/**
 * @brief Register a callback on a bytemap (void* variant).
 */
static inline int c_bytemap_register_callback(bytemap* map, bytemap_callback_func callback, void* user_data, uintptr_t* out_id) {
    return c_bytemap_ex_register_callback(map, callback, user_data, out_id);
}

/**
 * @brief Unregister a callback from a bytemap (void* variant).
 */
static inline int c_bytemap_unregister_callback(bytemap* map, uintptr_t callback_id) {
    return c_bytemap_ex_unregister_callback(map, callback_id);
}

/**
 * @brief Get a void* value from a bytemap by key.
 */
static inline int c_bytemap_get(const bytemap* map, const char* key, size_t key_len, void** out) {
    return c_bytemap_ex_get(map, key, key_len, (char*) out, NULL);
}

/**
 * @brief Test whether a key exists in a bytemap.
 */
static inline int c_bytemap_contains(const bytemap* map, const char* key, size_t key_len) {
    return c_bytemap_ex_contains(map, key, key_len);
}

/**
 * @brief Rehash a bytemap to a new capacity.
 */
static inline int c_bytemap_rehash(bytemap* map, size_t new_capacity) {
    return c_bytemap_ex_rehash(map, new_capacity, 0);
}

/**
 * @brief Insert or update a key/value pair in a bytemap (void* variant).
 *
 * @param seq_id  Sequence ID for callback self-suppression.
 */
static inline int c_bytemap_set(bytemap* map, const char* key, size_t key_len, void* value, bytemap_entry** out) {
    return c_bytemap_ex_set(map, key, key_len, (const char*) &value, sizeof(void*), 0, out);
}

/**
 * @brief Remove a key from a bytemap, returning its void* value.
 */
static inline int c_bytemap_pop(bytemap* map, const char* key, size_t key_len, void** out) {
    return c_bytemap_ex_pop(map, key, key_len, 0, (char*) out, NULL);
}

/**
 * @brief Get the number of live entries.
 */
static inline size_t c_bytemap_len(const bytemap* map) {
    return c_bytemap_ex_len(map);
}

/**
 * @brief Deep-clone a bytemap instance (void* variant).
 */
static inline bytemap* c_bytemap_clone(const bytemap* src, allocator_protocol* allocator) {
    return c_bytemap_ex_clone(src, allocator);
}

// ========== Iteration helpers (void* variant) ==========

static inline bytemap_entry* c_bytemap_first(const bytemap* map) {
    return c_bytemap_entry_first(map);
}

static inline bytemap_entry* c_bytemap_last(const bytemap* map) {
    return map ? map->last : NULL;
}

static inline bytemap_entry* c_bytemap_next(const bytemap_entry* entry) {
    return entry ? entry->next : NULL;
}

static inline bytemap_entry* c_bytemap_prev(const bytemap_entry* entry) {
    return entry ? entry->prev : NULL;
}

/**
 * @brief Convenience: get the void* value from an entry.
 */
static inline void* c_bytemap_entry_value(const bytemap_entry* entry) {
    if (!entry || !entry->occupied) return NULL;
    return *(void**) entry->value;
}

#endif  // C_BYTEMAP_H
