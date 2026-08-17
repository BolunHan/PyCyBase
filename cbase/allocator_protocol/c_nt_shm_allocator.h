#ifndef AP_SHM_C_NT_SHM_ALLOCATOR_H
#define AP_SHM_C_NT_SHM_ALLOCATOR_H

#ifndef _WIN32
#error "c_nt_shm_allocator.h is intended for Windows builds only"
#endif

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <tlhelp32.h>

#include "cbase/nt/pthread_nt_compat.h"

// ========== Configuration ==========

#ifndef AP_SHM_AUTOPAGE_CAPACITY
#define AP_SHM_AUTOPAGE_CAPACITY (64 * 1024) /* 64 KiB */
#endif

#ifndef AP_SHM_AUTOPAGE_CAPACITY_MAX
#define AP_SHM_AUTOPAGE_CAPACITY_MAX (16 * 1024 * 1024) /* 16 MiB */
#endif

#ifndef AP_SHM_AUTOPAGE_ALIGNMENT
#define AP_SHM_AUTOPAGE_ALIGNMENT (4 * 1024) /* 4 KiB */
#endif

#ifndef AP_SHM_ALLOCATOR_PREFIX
#define AP_SHM_ALLOCATOR_PREFIX "/c_cbase_shm"
#endif

#ifndef AP_SHM_NAME_LEN
#define AP_SHM_NAME_LEN 256
#endif

#ifndef AP_SHM_PREFIX_MAX
#define AP_SHM_PREFIX_MAX 64
#endif

#ifndef AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE
#define AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE (128ULL << 30) /* 128 GiB */
#endif

/* Size-binned free lists: exact 8-byte-granular bins for capacities up to
 * AP_SHM_EXACT_BIN_COUNT * 8 bytes, pow2-class bins above. */
#ifndef AP_SHM_EXACT_BIN_COUNT
#define AP_SHM_EXACT_BIN_COUNT 8192 /* capacity <= 64 KiB gets an exact bin */
#endif

#ifndef AP_SHM_LARGE_BIN_COUNT
#define AP_SHM_LARGE_BIN_COUNT 9 /* pow2-class bins for capacity > 64 KiB */
#endif

#define AP_SHM_BIN_COUNT (AP_SHM_EXACT_BIN_COUNT + AP_SHM_LARGE_BIN_COUNT + 1)

/* Miss-path page scaling cap: page sizes double from the current page up
 * to this cap; a request larger than the cap forces a bigger page.
 * Used only when AP_SHM_PAGE_FIT_TO_REQUEST is 0. */
#ifndef AP_SHM_PAGE_EXTEND_MAX
#define AP_SHM_PAGE_EXTEND_MAX (128 * 1024 * 1024) /* 128 MiB */
#endif

/* Miss-path page policy: 0 (default) = capped power-of-2 page scaling
 * (see AP_SHM_PAGE_EXTEND_MAX); 1 = fit the page to the request (floor
 * = autopage_capacity) so rare bin misses never extend oversized pages. */
#ifndef AP_SHM_PAGE_FIT_TO_REQUEST
#define AP_SHM_PAGE_FIT_TO_REQUEST 0
#endif

/* On an exact-bin miss, probe up to this many LARGER exact bins before
 * the page path.  A slightly larger block satisfies the request; on free
 * it returns to its own bin (recycling unaffected), and the fragmentation
 * is bounded by the probe range.  0 disables the probe. */
#ifndef AP_SHM_EXACT_BIN_PROBE_COUNT
#define AP_SHM_EXACT_BIN_PROBE_COUNT 2
#endif

/* On-start stale SHM scan: when c_nt_shm_allocator_new runs, sweep for
 * allocator and page mappings whose creator pid is dead (best-effort --
 * a mapping held by a live process is not destroyed).  0 disables the
 * scan (only c_nt_shm_clear_dangling called explicitly). */
#ifndef AP_SHM_STALE_CHECK
#define AP_SHM_STALE_CHECK 1
#endif

/* Close the section handle right after mapping (NT equivalent of
 * unlink-while-mapped): the view keeps the object alive for this process
 * and the kernel destroys it when the last view is unmapped -- a crashed
 * creator leaks nothing.  0 keeps objects openable by name until
 * c_nt_shm_allocator_free closes the handles. */
#ifndef AP_SHM_UNLINK_ON_MAP
#define AP_SHM_UNLINK_ON_MAP 1
#endif

// ========== Structs ==========

typedef struct nt_shm_page {
    size_t                      capacity;
    size_t                      occupied;
    size_t                      offset;
    struct nt_shm_allocator*    allocator;
    struct nt_shm_memory_block* allocated;
    char                        shm_name[AP_SHM_NAME_LEN];
    char                        prev_name[AP_SHM_NAME_LEN];
} nt_shm_page;

typedef struct nt_shm_page_ctx {
    nt_shm_page*            shm_page;
    HANDLE                  handle;
    char*                   buffer;
    struct nt_shm_page_ctx* prev;
} nt_shm_page_ctx;

typedef struct nt_shm_memory_block {
    size_t                      capacity;
    size_t                      size;
    struct nt_shm_memory_block* next_free;
    struct nt_shm_memory_block* next_allocated;
    nt_shm_page*                parent_page;
    char                        buffer[];
} nt_shm_memory_block;

typedef struct nt_shm_allocator {
    char                 shm_name[AP_SHM_NAME_LEN];
    size_t               pid;
    char                 lock_name[AP_SHM_NAME_LEN];
    size_t               mapped_size;
    char                 active_page[AP_SHM_NAME_LEN];
    size_t               mapped_pages;
    size_t               autopage_capacity;
    size_t               autopage_capacity_max;
    size_t               autopage_alignment;
    nt_shm_memory_block* bins[AP_SHM_BIN_COUNT];
    char                 shm_prefix[AP_SHM_PREFIX_MAX];
    pthread_mutex_t      lock;  // dummy; present for c_allocator_protocol.h compat
} nt_shm_allocator;

typedef struct nt_shm_allocator_ctx {
    nt_shm_allocator* shm_allocator;
    HANDLE            shm_handle;
    HANDLE            lock_handle;
    nt_shm_page_ctx*  active_page;
} nt_shm_allocator_ctx;

// ========== Internal Helpers ==========

static const size_t c_nt_shm_page_overhead = (sizeof(nt_shm_page) + sizeof(void*) - 1) & ~(sizeof(void*) - 1);
static const size_t c_nt_shm_block_overhead = (sizeof(nt_shm_memory_block) + sizeof(void*) - 1) & ~(sizeof(void*) - 1);

/**
 * @brief Convert a UTF-8 name to a wide-char name with "Global\\" prefix.
 * @param utf8_name UTF-8 input name (e.g. "/c_cbase_shm_ac_1234_7f...").
 * @param wide_out Output buffer for wide-char name (must be at least AP_SHM_NAME_LEN WCHARs).
 * @return Number of WCHARs written (excluding null terminator), or 0 on error.
 */
static inline int c_nt_shm_to_wide(const char* utf8_name, wchar_t* wide_out) {
    if (!utf8_name || !wide_out) return 0;

    // Skip leading '/' in POSIX-style names
    const char* src = utf8_name;
    if (src[0] == '/') src++;

    // Prepend "Global\\"
    wchar_t* dst = wide_out;
    wcscpy(dst, L"Global\\");
    dst += 7;

    // Convert ASCII to wide chars
    int count = 7;
    while (*src && count < AP_SHM_NAME_LEN - 1) {
        *dst++ = (wchar_t) (unsigned char) *src++;
        count++;
    }
    *dst = L'\0';
    return count;
}

/**
 * @brief Lock the allocator via the cached named mutex handle.
 */
static inline int c_nt_shm_lock(nt_shm_allocator_ctx* ctx) {
    if (!ctx || !ctx->lock_handle) return -1;
    DWORD result = WaitForSingleObject(ctx->lock_handle, INFINITE);
    return (result == WAIT_OBJECT_0) ? 0 : -1;
}

/**
 * @brief Unlock the allocator via the cached named mutex handle.
 */
static inline void c_nt_shm_unlock(nt_shm_allocator_ctx* ctx) {
    if (ctx && ctx->lock_handle) {
        ReleaseMutex(ctx->lock_handle);
    }
}

// ========== Utility Functions ==========

static inline size_t c_nt_shm_page_roundup(nt_shm_allocator* allocator, size_t size) {
    return (size + allocator->autopage_alignment - 1) & ~(allocator->autopage_alignment - 1);
}

static inline size_t c_nt_shm_block_roundup(size_t size) {
    return (size + sizeof(void*) - 1) & ~(sizeof(void*) - 1);
}

/* ceil(log2(v)) for 0 < v <= UINT32_MAX.
 * 32-bit is sufficient: the bin structure caps block capacities well below
 * 4 GiB, so a narrower parameter type truthfully advertises the domain. */
static inline size_t c_nt_shm_block_ceil_log2(uint32_t v) {
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
 * Exact bins: index = capacity / 8 (1..AP_SHM_EXACT_BIN_COUNT), so any
 * block in bin(cap_net) has capacity == cap_net and always fits.
 * Larger capacities: pow2-class bins keyed by ceil(log2(capacity))
 * (indices AP_SHM_EXACT_BIN_COUNT+1..); the last bin is the overflow
 * class.  In-bin first-fit is used there (blocks can be up to one class
 * smaller than the request). */
static inline size_t c_nt_shm_block_bin(size_t capacity) {
    if (capacity <= (size_t) AP_SHM_EXACT_BIN_COUNT * 8u) {
        return capacity >> 3;
    }
    size_t idx = (size_t) AP_SHM_EXACT_BIN_COUNT + (c_nt_shm_block_ceil_log2(capacity) - 16u);
    if (idx > (size_t) AP_SHM_EXACT_BIN_COUNT + AP_SHM_LARGE_BIN_COUNT) {
        idx = (size_t) AP_SHM_EXACT_BIN_COUNT + AP_SHM_LARGE_BIN_COUNT;
    }
    return idx;
}

static inline void c_nt_shm_allocator_name(const char* shm_prefix, char* out) {
    DWORD pid = GetCurrentProcessId();
    snprintf(out, AP_SHM_NAME_LEN, "%s_ac_%lx", shm_prefix, (unsigned long) pid);
}

static inline void c_nt_shm_page_name(nt_shm_allocator* allocator, char* out) {
    DWORD  pid = GetCurrentProcessId();
    size_t page_idx = allocator->mapped_pages;
    snprintf(out, AP_SHM_NAME_LEN, "%s_pg_%lx_%lx_%zx", allocator->shm_prefix, (unsigned long) pid, (unsigned long) (uintptr_t) allocator, page_idx);
}

static inline void c_nt_shm_mutex_name(const char* shm_prefix, char* out) {
    DWORD pid = GetCurrentProcessId();
    snprintf(out, AP_SHM_NAME_LEN, "%s_mtx_%lx", shm_prefix, (unsigned long) pid);
}

// ========== Scan / Dangling ==========

/**
 * @brief Try to open a file mapping with the given name pattern.
 *
 * Iterates through candidate PIDs to find a matching file mapping.
 * Uses the naming convention: {prefix}_{suffix}_{pid}
 *
 * @param prefix UTF-8 prefix (e.g. "/c_cbase_shm_ac").
 * @param out Output buffer to receive the found UTF-8 name.
 * @param out_len Size of output buffer.
 * @return 0 on success, -1 with errno set otherwise.
 */
static inline int c_nt_shm_scan(const char* prefix, const char* suffix, char* out, size_t out_len) {
    if (!prefix || !out || !out_len) {
        errno = EINVAL;
        return -1;
    }

    // Skip leading '/'
    const char* pfx = prefix;
    if (pfx[0] == '/') pfx++;

    // The full prefix is {prefix}_{suffix}
    char full_prefix[AP_SHM_NAME_LEN];
    if (suffix) {
        snprintf(full_prefix, sizeof(full_prefix), "%s_%s", pfx, suffix);
    }
    else {
        strncpy(full_prefix, pfx, sizeof(full_prefix) - 1);
        full_prefix[sizeof(full_prefix) - 1] = '\0';
    }

    // Build wide prefix: "Global\\{full_prefix}_"
    wchar_t wide_prefix[AP_SHM_NAME_LEN];
    int     prefix_len = swprintf(wide_prefix, AP_SHM_NAME_LEN, L"Global\\%hs_", full_prefix);
    if (prefix_len < 0) {
        errno = EINVAL;
        return -1;
    }

    // Try current process and a range of nearby PIDs
    DWORD current_pid = GetCurrentProcessId();
    for (DWORD offset = 0; offset < 65536; offset++) {
        DWORD try_pid = (current_pid + offset) % 65536;
        if (try_pid == 0) continue;

        wchar_t wide_name[AP_SHM_NAME_LEN];
        swprintf(wide_name, AP_SHM_NAME_LEN, L"Global\\%hs_%lx", full_prefix, (unsigned long) try_pid);

        HANDLE h = OpenFileMappingW(FILE_MAP_READ, FALSE, wide_name);
        if (h != NULL) {
            CloseHandle(h);
            // Convert back to UTF-8
            int ret = WideCharToMultiByte(CP_UTF8, 0, wide_name, -1, out, (int) out_len, NULL, NULL);
            if (ret > 0) {
                return 0;
            }
        }
    }

    errno = ENOENT;
    return -1;
}

/**
 * @brief Scan for an allocator SHM name (appends "_ac" to prefix).
 */
static inline int c_nt_shm_scan_allocator(const char* shm_prefix, char* out) {
    if (!shm_prefix) shm_prefix = AP_SHM_ALLOCATOR_PREFIX;
    return c_nt_shm_scan(shm_prefix, "ac", out, AP_SHM_NAME_LEN);
}

/**
 * @brief Scan for a page SHM name (appends "_pg" to prefix).
 */
static inline int c_nt_shm_scan_page(const char* shm_prefix, char* out) {
    if (!shm_prefix) shm_prefix = AP_SHM_ALLOCATOR_PREFIX;
    return c_nt_shm_scan(shm_prefix, "pg", out, AP_SHM_NAME_LEN);
}

/**
 * @brief Extract pid embedded in allocator/page SHM name.
 */
static inline DWORD c_nt_shm_pid(const char* shm_name) {
    if (!shm_name) {
        errno = EINVAL;
        return 0;
    }

    const char* base = shm_name;
    // Skip "Global\" prefix if present
    if (strncmp(base, "Global\\", 7) == 0) base += 7;
    if (base[0] == '/') base++;

    // Name format: {prefix}_{pid_hex}_{suffix} or {prefix}_{pid_hex}
    const char* suffix_us = strrchr(base, '_');
    if (!suffix_us) {
        errno = EINVAL;
        return 0;
    }

    const char* pid_us = NULL;
    for (const char* p = base; p < suffix_us; p++) {
        if (*p == '_') pid_us = p;
    }
    if (!pid_us) {
        errno = EINVAL;
        return 0;
    }

    const char* pid_start = pid_us + 1;
    size_t      pid_len = (size_t) (suffix_us - pid_start);
    if (pid_len == 0 || pid_len >= 32) {
        errno = EINVAL;
        return 0;
    }

    char pidbuf[32];
    memcpy(pidbuf, pid_start, pid_len);
    pidbuf[pid_len] = '\0';

    errno = 0;
    char*         endptr = NULL;
    unsigned long v = strtoul(pidbuf, &endptr, 16);
    if (errno != 0 || endptr == pidbuf || *endptr != '\0') {
        errno = EINVAL;
        return 0;
    }

    return (DWORD) v;
}

/**
 * @brief Check if a process is still running.
 */
static inline int c_nt_shm_process_alive(DWORD pid) {
    if (pid == 0) return 0;
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return 0;
    DWORD exit_code;
    BOOL  ok = GetExitCodeProcess(h, &exit_code);
    CloseHandle(h);
    return ok && exit_code == STILL_ACTIVE;
}

/**
 * @brief Find and map a dangling allocator (whose creator pid is gone).
 */
static inline nt_shm_allocator* c_nt_shm_allocator_dangling(const char* shm_prefix, char* shm_name) {
    if (!shm_name) {
        errno = EINVAL;
        return NULL;
    }

    if (!shm_prefix) shm_prefix = AP_SHM_ALLOCATOR_PREFIX;

    // Build wide prefix: "Global\\{shm_prefix}_ac_"
    const char* pfx = shm_prefix;
    if (pfx[0] == '/') pfx++;

    wchar_t wide_prefix[AP_SHM_NAME_LEN];
    swprintf(wide_prefix, AP_SHM_NAME_LEN, L"Global\\%hs_ac_", pfx);

    // Scan PIDs
    DWORD current_pid = GetCurrentProcessId();
    for (DWORD offset = 0; offset < 65536; offset++) {
        DWORD try_pid = (current_pid + offset) % 65536;
        if (try_pid == 0) continue;

        wchar_t wide_name[AP_SHM_NAME_LEN];
        swprintf(wide_name, AP_SHM_NAME_LEN, L"Global\\%hs_ac_%lx", pfx, (unsigned long) try_pid);

        if (c_nt_shm_process_alive(try_pid)) continue;

        HANDLE h = OpenFileMappingW(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, wide_name);
        if (!h) continue;

        void* map = MapViewOfFile(h, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(nt_shm_allocator));
        if (!map) {
            CloseHandle(h);
            continue;
        }

        // Convert wide name back to UTF-8 for output
        WideCharToMultiByte(CP_UTF8, 0, wide_name, -1, shm_name, AP_SHM_NAME_LEN, NULL, NULL);
        fprintf(stderr, "[AP] [STALE_SHM] map dangling allocator %s (pid %lu, dead)\n",
                shm_name, (unsigned long) try_pid);
        return (nt_shm_allocator*) map;
    }

    errno = ENOENT;
    return NULL;
}

/**
 * @brief Unlink all dangling allocator/page SHM objects.
 *
 * On Windows, file mappings are destroyed when all handles are closed.
 * This function attempts to open and close any dangling objects, but
 * the actual cleanup happens when the last handle is closed.
 */
static inline void c_nt_shm_clear_dangling(const char* shm_prefix) {
#if AP_SHM_STALE_CHECK
    if (!shm_prefix) shm_prefix = AP_SHM_ALLOCATOR_PREFIX;

    const char* pfx = shm_prefix;
    if (pfx[0] == '/') pfx++;

    // Live-pid bitmap from a single Toolhelp32 snapshot: avoids 65k
    // OpenProcess probes per scan.  NULL means "snapshot failed" and
    // forces the per-pid probe fallback below.
    unsigned char* alive = (unsigned char*) calloc(1, 65536 / 8);
    if (alive) {
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snap != INVALID_HANDLE_VALUE) {
            PROCESSENTRY32W pe;
            pe.dwSize = sizeof(pe);
            if (Process32FirstW(snap, &pe)) {
                do {
                    DWORD pid = pe.th32ProcessID;
                    if (pid < 65536) {
                        alive[pid >> 3] |= (unsigned char) (1u << (pid & 7));
                    }
                } while (Process32NextW(snap, &pe));
            }
            CloseHandle(snap);
        }
        else {
            free(alive);
            alive = NULL;  // fall back to per-pid probing
        }
    }

    const char* suffixes[] = {"ac", "pg"};
    size_t      suffix_count = 2;

    for (DWORD offset = 0; offset < 65536; offset++) {
        DWORD try_pid = (GetCurrentProcessId() + offset) % 65536;
        if (try_pid == 0) continue;

        if (alive) {
            if ((alive[try_pid >> 3] >> (try_pid & 7)) & 1u) continue;
        }
        else if (c_nt_shm_process_alive(try_pid)) {
            continue;
        }

        for (size_t i = 0; i < suffix_count; i++) {
            wchar_t wide_name[AP_SHM_NAME_LEN];
            swprintf(wide_name, AP_SHM_NAME_LEN, L"Global\\%hs_%hs_%lx", pfx, suffixes[i], (unsigned long) try_pid);

            HANDLE h = OpenFileMappingW(FILE_MAP_READ, FALSE, wide_name);
            if (h) {
                CloseHandle(h);  // Closing our handle helps destroy the mapping
                char utf8_name[AP_SHM_NAME_LEN];
                if (WideCharToMultiByte(CP_UTF8, 0, wide_name, -1, utf8_name, AP_SHM_NAME_LEN, NULL, NULL) > 0) {
                    fprintf(stderr, "[AP] [STALE_SHM] close dangling mapping %s (pid %lu, dead)\n",
                            utf8_name, (unsigned long) try_pid);
                }
            }
        }
    }

    free(alive);
#else
    (void) shm_prefix;
#endif
}

// ========== Page Management ==========

static inline nt_shm_page_ctx* c_nt_shm_page_new(nt_shm_allocator* allocator, size_t page_capacity) {
    nt_shm_page_ctx* ctx = (nt_shm_page_ctx*) calloc(1, sizeof(nt_shm_page_ctx));
    if (!ctx) return NULL;

    nt_shm_page* meta = (nt_shm_page*) calloc(1, c_nt_shm_page_overhead);
    if (!meta) {
        free(ctx);
        return NULL;
    }
    ctx->shm_page = meta;

    meta->capacity = page_capacity;
    meta->occupied = c_nt_shm_page_overhead;
    meta->offset = 0;

    c_nt_shm_page_name(allocator, meta->shm_name);

    // Create named file mapping for the page
    wchar_t wide_name[AP_SHM_NAME_LEN];
    if (c_nt_shm_to_wide(meta->shm_name, wide_name) == 0) {
        free(meta);
        free(ctx);
        return NULL;
    }

    DWORD  size_high = (DWORD) (page_capacity >> 32);
    DWORD  size_low = (DWORD) (page_capacity & 0xFFFFFFFF);

    HANDLE hMapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        NULL,
        PAGE_READWRITE,
        size_high,
        size_low,
        wide_name
    );

    if (!hMapping) {
        free(meta);
        free(ctx);
        return NULL;
    }

    ctx->shm_page = meta;
    ctx->handle = hMapping;
    ctx->buffer = NULL;
    ctx->prev = NULL;

    return ctx;
}

static inline int c_nt_shm_page_map(nt_shm_allocator* allocator, nt_shm_page_ctx* page_ctx) {
    if (!allocator || !page_ctx || !page_ctx->shm_page || !page_ctx->handle) {
        errno = EINVAL;
        return -1;
    }

    size_t page_capacity = page_ctx->shm_page->capacity;
    size_t offset = allocator->mapped_size;

    // Map view of the file mapping
    void* mapped = MapViewOfFile(page_ctx->handle, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, page_capacity);
    if (!mapped) {
        return -1;
    }

#if AP_SHM_UNLINK_ON_MAP
    // Close the section handle (see c_nt_shm_allocator_new): the view
    // keeps the page alive for this process -- a crash leaks nothing.
    CloseHandle(page_ctx->handle);
    page_ctx->handle = NULL;
#endif

    // Copy metadata to start of mapped page
    nt_shm_page* page_meta = (nt_shm_page*) mapped;
    memcpy(page_meta, page_ctx->shm_page, c_nt_shm_page_overhead);
    free(page_ctx->shm_page);
    page_ctx->shm_page = page_meta;
    page_ctx->buffer = (char*) mapped;

    // Set correct offset and linkage
    page_meta->offset = offset;
    page_meta->allocator = allocator;

    if (allocator->mapped_pages == 0) {
        page_meta->prev_name[0] = '\0';
    }
    else {
        memcpy(page_meta->prev_name, allocator->active_page, AP_SHM_NAME_LEN);
        page_meta->prev_name[AP_SHM_NAME_LEN - 1] = '\0';
    }

    allocator->mapped_size += page_capacity;
    memcpy(allocator->active_page, page_meta->shm_name, AP_SHM_NAME_LEN);
    allocator->active_page[AP_SHM_NAME_LEN - 1] = '\0';
    allocator->mapped_pages++;

    return 0;
}

static inline void c_nt_shm_page_reclaim(nt_shm_allocator* allocator, nt_shm_page_ctx* page_ctx) {
    if (!allocator || !page_ctx || !page_ctx->shm_page) {
        errno = EINVAL;
        return;
    }

    nt_shm_page*          page = page_ctx->shm_page;

    nt_shm_memory_block** prevp = &page->allocated;
    while (*prevp) {
        nt_shm_memory_block* block = *prevp;
        if (block->size != 0) break;

        *prevp = block->next_allocated;
        block->next_allocated = NULL;

        nt_shm_memory_block** free_prev = &allocator->bins[c_nt_shm_block_bin(block->capacity)];
        while (*free_prev && *free_prev != block) {
            free_prev = &(*free_prev)->next_free;
        }
        if (*free_prev == block) {
            *free_prev = block->next_free;
        }
        block->next_free = NULL;

        size_t cap_total = block->capacity + c_nt_shm_block_overhead;
        if (page->occupied >= cap_total) {
            page->occupied -= cap_total;
        }
    }
}

// ========== Public API ==========

/**
 * @brief Extend allocator with a new page, locking via pthread_mutex if provided.
 */
static inline nt_shm_page_ctx* c_nt_shm_allocator_extend(nt_shm_allocator_ctx* ctx, size_t capacity, pthread_mutex_t* lock) {
    if (!ctx || !ctx->shm_allocator) {
        errno = EINVAL;
        return NULL;
    }

    nt_shm_allocator* allocator = ctx->shm_allocator;
    uint8_t           locked = 0;

    if (lock) {
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return NULL;
        }
        locked = 1;
    }

    // Determine new page capacity
    if (capacity == 0) {
        if (!ctx->active_page) {
            capacity = allocator->autopage_capacity;
        }
        else {
            size_t prev_cap = ctx->active_page->shm_page->capacity;
            capacity = prev_cap * 2;
            if (capacity < allocator->autopage_capacity) {
                capacity = allocator->autopage_capacity;
            }
            else if (capacity > allocator->autopage_capacity_max) {
                capacity = allocator->autopage_capacity_max;
            }
        }
    }

    size_t aligned_capacity = c_nt_shm_page_roundup(allocator, capacity);

    // Create new page
    nt_shm_page_ctx* page_ctx = c_nt_shm_page_new(allocator, aligned_capacity);
    if (!page_ctx) {
        if (locked) pthread_mutex_unlock(lock);
        return NULL;
    }

    // Map new page
    if (c_nt_shm_page_map(allocator, page_ctx) != 0) {
        CloseHandle(page_ctx->handle);
        free(page_ctx->shm_page);
        free(page_ctx);
        if (locked) pthread_mutex_unlock(lock);
        return NULL;
    }

    // Update context
    page_ctx->prev = ctx->active_page;
    ctx->active_page = page_ctx;

    if (locked) pthread_mutex_unlock(lock);
    return page_ctx;
}

/**
 * @brief Create a new NT SHM allocator.
 * @param region_size Ignored on NT (pages are independently mapped).
 * @param shm_prefix Custom SHM name prefix (NULL for compile-time default).
 * @return Allocator context or NULL on failure.
 */
static inline nt_shm_allocator_ctx* c_nt_shm_allocator_new(size_t region_size, const char* shm_prefix) {
    (void) region_size;  // Not used on NT -- pages are independently mapped

    nt_shm_allocator_ctx* ctx = (nt_shm_allocator_ctx*) calloc(1, sizeof(nt_shm_allocator_ctx));
    if (!ctx) return NULL;

    if (!shm_prefix) shm_prefix = AP_SHM_ALLOCATOR_PREFIX;

    size_t prefix_len = strnlen(shm_prefix, AP_SHM_PREFIX_MAX);
    if (prefix_len >= AP_SHM_PREFIX_MAX) {
        fprintf(stderr, "c_nt_shm_allocator_new: shm_prefix exceeds AP_SHM_PREFIX_MAX (%zu)\n", (size_t) AP_SHM_PREFIX_MAX);
        abort();
    }

#if AP_SHM_STALE_CHECK
    // On-start stale scan: sweep mappings left behind by dead creators
    // before creating our own (best-effort on NT).
    c_nt_shm_clear_dangling(shm_prefix);
#endif

    // Step 1: Create named file mapping for allocator metadata
    char meta_shm_name[AP_SHM_NAME_LEN];
    c_nt_shm_allocator_name(shm_prefix, meta_shm_name);

    wchar_t wide_meta_name[AP_SHM_NAME_LEN];
    if (c_nt_shm_to_wide(meta_shm_name, wide_meta_name) == 0) {
        free(ctx);
        return NULL;
    }

    HANDLE meta_hMapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE,
        0, sizeof(nt_shm_allocator), wide_meta_name
    );

    if (!meta_hMapping) {
        free(ctx);
        return NULL;
    }

    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        // A live peer already owns this name.  Opening and wiping its meta
        // would corrupt the peer's allocator -- fail cleanly instead.
        CloseHandle(meta_hMapping);
        free(ctx);
        errno = EEXIST;
        return NULL;
    }

    // Step 2: Map allocator metadata into memory
    nt_shm_allocator* meta = (nt_shm_allocator*) MapViewOfFile(
        meta_hMapping, FILE_MAP_READ | FILE_MAP_WRITE,
        0, 0, sizeof(nt_shm_allocator)
    );

    if (!meta) {
        CloseHandle(meta_hMapping);
        free(ctx);
        return NULL;
    }

    // Step 3: Initialize metadata in shared memory
    memset(meta, 0, sizeof(nt_shm_allocator));

    size_t name_len = strnlen(meta_shm_name, AP_SHM_NAME_LEN - 1);
    memcpy(meta->shm_name, meta_shm_name, name_len);
    meta->shm_name[name_len] = '\0';
    meta->pid = (size_t) GetCurrentProcessId();
    meta->mapped_size = 0;
    meta->mapped_pages = 0;
    meta->active_page[0] = '\0';
    meta->autopage_capacity = AP_SHM_AUTOPAGE_CAPACITY;
    meta->autopage_capacity_max = AP_SHM_AUTOPAGE_CAPACITY_MAX;
    meta->autopage_alignment = AP_SHM_AUTOPAGE_ALIGNMENT;

    memcpy(meta->shm_prefix, shm_prefix, prefix_len);
    meta->shm_prefix[prefix_len] = '\0';

    // Step 4: Create named mutex for inter-process synchronization
    c_nt_shm_mutex_name(shm_prefix, meta->lock_name);
    meta->lock_name[AP_SHM_NAME_LEN - 1] = '\0';

    wchar_t wide_mutex_name[AP_SHM_NAME_LEN];
    if (c_nt_shm_to_wide(meta->lock_name, wide_mutex_name) == 0) {
        UnmapViewOfFile(meta);
        CloseHandle(meta_hMapping);
        free(ctx);
        return NULL;
    }

    HANDLE lock_handle = CreateMutexW(NULL, FALSE, wide_mutex_name);
    if (!lock_handle) {
        UnmapViewOfFile(meta);
        CloseHandle(meta_hMapping);
        free(ctx);
        return NULL;
    }

    // Step 5: Initialize intra-process mutex (CRITICAL_SECTION via pthread compat)
    if (pthread_mutex_init(&meta->lock, NULL) != 0) {
        CloseHandle(lock_handle);
        UnmapViewOfFile(meta);
        CloseHandle(meta_hMapping);
        free(ctx);
        return NULL;
    }

    // Step 6: Fill context
    ctx->shm_allocator = meta;
    ctx->shm_handle = meta_hMapping;
    ctx->lock_handle = lock_handle;
    ctx->active_page = NULL;

#if AP_SHM_UNLINK_ON_MAP
    // Close the section handle: the mapped view keeps the object alive
    // for this process, and the kernel destroys it when the last view is
    // unmapped -- a crashed creator leaks nothing.
    CloseHandle(meta_hMapping);
    ctx->shm_handle = NULL;
#endif

    return ctx;
}

/**
 * @brief Tear down allocator, unmapping pages and closing handles.
 */
static inline void c_nt_shm_allocator_free(nt_shm_allocator_ctx* ctx) {
    if (!ctx) return;

    // Step 1: Unmap all pages
    nt_shm_page_ctx* page_ctx = ctx->active_page;
    while (page_ctx) {
        nt_shm_page_ctx* prev = page_ctx->prev;
        nt_shm_page*     page_meta = page_ctx->shm_page;

        if (page_meta) {
            UnmapViewOfFile((void*) page_meta);
        }

        if (page_ctx->handle) {
            CloseHandle(page_ctx->handle);
        }

        free(page_ctx);
        page_ctx = prev;
    }

    // Step 2: Unmap allocator metadata
    nt_shm_allocator* allocator = ctx->shm_allocator;
    if (allocator) {
        pthread_mutex_destroy(&allocator->lock);
        UnmapViewOfFile((void*) allocator);
    }

    // Step 3: Close handles
    if (ctx->shm_handle) CloseHandle(ctx->shm_handle);
    if (ctx->lock_handle) CloseHandle(ctx->lock_handle);

    // Step 4: Free context
    free(ctx);
}

static inline void* c_nt_shm_calloc(nt_shm_allocator_ctx* ctx, size_t size, pthread_mutex_t* lock) {
    if (!ctx || !ctx->shm_allocator || size == 0) {
        errno = EINVAL;
        return NULL;
    }

    size_t            cap_net = c_nt_shm_block_roundup(size);
    size_t            cap_total = cap_net + c_nt_shm_block_overhead;
    nt_shm_allocator* allocator = ctx->shm_allocator;

    uint8_t           locked = 0;
    pthread_mutex_t*  builtin_lock = &allocator->lock;
    pthread_mutex_t*  child_lock = &allocator->lock;
    if (lock) {
        if (lock == builtin_lock) child_lock = NULL;
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

    // Ensure there's an active page with space
    nt_shm_page_ctx* page_ctx = ctx->active_page;
    if (!page_ctx) {
        size_t target_cap = allocator->autopage_capacity;
        while (target_cap < cap_total + c_nt_shm_page_overhead) {
            target_cap *= 2;
        }

        page_ctx = c_nt_shm_allocator_extend(ctx, target_cap, child_lock);
        if (!page_ctx) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
    }

    nt_shm_page* page_meta = page_ctx->shm_page;

    if (page_meta->occupied + cap_total > page_meta->capacity) {
        size_t target_cap = page_meta->capacity;
        if (target_cap < allocator->autopage_capacity) {
            target_cap = allocator->autopage_capacity;
        }
        else if (target_cap < allocator->autopage_capacity_max) {
            target_cap *= 2;
        }

        while (target_cap < cap_total + c_nt_shm_page_overhead) {
            target_cap *= 2;
        }
        page_ctx = c_nt_shm_allocator_extend(ctx, target_cap, child_lock);
        if (!page_ctx) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
        page_meta = page_ctx->shm_page;
    }

    // Allocate from active page
    size_t               offset = page_meta->occupied;
    nt_shm_memory_block* block = (nt_shm_memory_block*) (page_ctx->buffer + offset);
    block->capacity = cap_net;
    block->size = size;
    block->next_free = NULL;
    block->parent_page = page_meta;
    block->next_allocated = page_meta->allocated;
    page_meta->allocated = block;
    page_meta->occupied += cap_total;

    if (locked) pthread_mutex_unlock(lock);

    memset(block + 1, 0, cap_net);
    return (void*) block->buffer;
}

static inline void* c_nt_shm_request(nt_shm_allocator_ctx* ctx, size_t size, int scan_all_pages, pthread_mutex_t* lock) {
    if (!ctx || !ctx->shm_allocator || size == 0) {
        errno = EINVAL;
        return NULL;
    }

    size_t            cap_net = c_nt_shm_block_roundup(size);
    size_t            cap_total = cap_net + c_nt_shm_block_overhead;
    nt_shm_allocator* allocator = ctx->shm_allocator;

    uint8_t           locked = 0;
    pthread_mutex_t*  builtin_lock = &allocator->lock;
    pthread_mutex_t*  child_lock = &allocator->lock;
    if (lock) {
        if (lock == builtin_lock) child_lock = NULL;
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

    // Step 1: Size-binned free-list reuse (see c_nt_shm_block_bin).
    // Exact bins always fit (capacity == cap_net) — O(1) head pop.
    // Pow2-class bins use in-bin first-fit: bins are short and same-
    // shaped, so the head is the common hit; larger-capacity blocks in
    // the bin also satisfy smaller requests.
    size_t               bin = c_nt_shm_block_bin(cap_net);
    nt_shm_memory_block* free_blk;
    if (bin <= (size_t) AP_SHM_EXACT_BIN_COUNT) {
        size_t found = bin;
        free_blk = allocator->bins[bin];
        if (!free_blk && AP_SHM_EXACT_BIN_PROBE_COUNT > 0) {
            size_t probe_end = bin + (size_t) AP_SHM_EXACT_BIN_PROBE_COUNT;
            if (probe_end > (size_t) AP_SHM_EXACT_BIN_COUNT) {
                probe_end = (size_t) AP_SHM_EXACT_BIN_COUNT;
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
        nt_shm_memory_block** prevp = &allocator->bins[bin];
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

    // Step 2: Locate a page with enough space
    nt_shm_page_ctx* target_ctx = NULL;
    if (scan_all_pages) {
        nt_shm_page_ctx* iter = ctx->active_page;
        while (iter) {
            nt_shm_page* meta = iter->shm_page;
            if (meta && meta->occupied + cap_total <= meta->capacity) {
                target_ctx = iter;
                break;
            }
            iter = iter->prev;
        }
    }
    else if (ctx->active_page) {
        nt_shm_page* meta = ctx->active_page->shm_page;
        if (meta && meta->occupied + cap_total <= meta->capacity) {
            target_ctx = ctx->active_page;
        }
    }

    // Step 3: Extend if no page fits
    if (!target_ctx) {
        size_t target_cap;
#if AP_SHM_PAGE_FIT_TO_REQUEST
        // Fit the page to the request (floor = autopage_capacity): rare
        // bin misses must not extend oversized pages.
        target_cap = allocator->autopage_capacity;
#else
        // Page scaling with a cap: double from the current page size up to
        // AP_SHM_PAGE_EXTEND_MAX.  A page larger than the cap (e.g. from
        // a huge request) scales back down to the cap.  Requests larger
        // than the cap force a bigger page via the fit loop below.
        nt_shm_page_ctx* current = ctx->active_page;
        if (!current) {
            target_cap = allocator->autopage_capacity;
        }
        else {
            target_cap = current->shm_page->capacity;
            if (target_cap < allocator->autopage_capacity) {
                target_cap = allocator->autopage_capacity;
            }
            else if (target_cap > (size_t) AP_SHM_PAGE_EXTEND_MAX) {
                target_cap = (size_t) AP_SHM_PAGE_EXTEND_MAX;
            }
            else if (target_cap < (size_t) AP_SHM_PAGE_EXTEND_MAX) {
                target_cap *= 2;
                if (target_cap > (size_t) AP_SHM_PAGE_EXTEND_MAX) {
                    target_cap = (size_t) AP_SHM_PAGE_EXTEND_MAX;
                }
            }
        }
#endif
        while (target_cap < cap_total + c_nt_shm_page_overhead) {
            target_cap *= 2;
        }

        target_ctx = c_nt_shm_allocator_extend(ctx, target_cap, child_lock);
        if (!target_ctx) {
            if (locked) pthread_mutex_unlock(lock);
            return NULL;
        }
    }

    // Step 4: Allocate from target page
    nt_shm_page*         page_meta = target_ctx->shm_page;
    size_t               offset = page_meta->occupied;
    nt_shm_memory_block* block = (nt_shm_memory_block*) (target_ctx->buffer + offset);
    block->capacity = cap_net;
    block->size = size;
    block->next_free = NULL;
    block->parent_page = page_meta;
    block->next_allocated = page_meta->allocated;
    page_meta->allocated = block;
    page_meta->occupied += cap_total;

    if (locked) pthread_mutex_unlock(lock);

    memset(block + 1, 0, cap_net);
    return (void*) block->buffer;
}

static inline void c_nt_shm_free(void* ptr, pthread_mutex_t* lock) {
    if (!ptr) {
        errno = EINVAL;
        return;
    }

    nt_shm_memory_block* block = (nt_shm_memory_block*) ((char*) ptr - c_nt_shm_block_overhead);
    nt_shm_page*         page = block->parent_page;
    if (!page || !page->allocator) {
        errno = EINVAL;
        return;
    }

    nt_shm_allocator* allocator = page->allocator;

    uint8_t           locked = 0;
    if (lock) {
        int ret = pthread_mutex_lock(lock);
        if (ret != 0) {
            errno = ret;
            return;
        }
        locked = 1;
    }

    block->size = 0;
    size_t bin = c_nt_shm_block_bin(block->capacity);
    block->next_free = allocator->bins[bin];
    allocator->bins[bin] = block;

    if (locked) pthread_mutex_unlock(lock);
}

static inline void c_nt_shm_reclaim(nt_shm_allocator_ctx* ctx, pthread_mutex_t* lock) {
    if (!ctx || !ctx->shm_allocator) {
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

    nt_shm_allocator* allocator = ctx->shm_allocator;
    nt_shm_page_ctx*  page_ctx = ctx->active_page;
    while (page_ctx) {
        c_nt_shm_page_reclaim(allocator, page_ctx);
        page_ctx = page_ctx->prev;
    }

    if (locked) pthread_mutex_unlock(lock);
}

#endif  // AP_SHM_C_NT_SHM_ALLOCATOR_H
