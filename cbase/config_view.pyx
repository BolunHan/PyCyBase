# config_view.pyx — compile-time macro registry for PyCyBase
#
# Exposes every overridable compile-time constant as a read-only,
# per-submodule nested mappingproxy (CONFIG_VIEW) so that downstream code
# and diagnostics can inspect the build configuration at runtime.

from cbase.allocator_protocol.c_allocator_protocol cimport (
    AP_ALLOC_VIGILANT, AP_ALLOC_MAGIC, AP_DEALLOC_MAGIC, AP_DECREF_AUTOFREE,
    AP_ALLOC_WITH_LOCK, AP_ALLOC_WITH_SHM, AP_ALLOC_WITH_FREELIST,
)
from cbase.allocator_protocol.c_heap_allocator cimport (
    AP_HEAP_AUTOPAGE_CAPACITY, AP_HEAP_AUTOPAGE_CAPACITY_MAX, AP_HEAP_AUTOPAGE_ALIGNMENT,
    AP_HEAP_EXACT_BIN_COUNT, AP_HEAP_LARGE_BIN_COUNT, AP_HEAP_BIN_COUNT,
    AP_HEAP_PAGE_EXTEND_MAX, AP_HEAP_PAGE_FIT_TO_REQUEST, AP_HEAP_EXACT_BIN_PROBE_COUNT,
)
from cbase.allocator_protocol.c_shm_comp cimport (
    AP_SHM_AUTOPAGE_CAPACITY, AP_SHM_AUTOPAGE_CAPACITY_MAX, AP_SHM_AUTOPAGE_ALIGNMENT,
    AP_SHM_ALLOCATOR_PREFIX, AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE,
    AP_SHM_NAME_LEN, AP_SHM_PREFIX_MAX,
    AP_SHM_EXACT_BIN_COUNT, AP_SHM_LARGE_BIN_COUNT, AP_SHM_BIN_COUNT,
    AP_SHM_PAGE_EXTEND_MAX, AP_SHM_PAGE_FIT_TO_REQUEST, AP_SHM_EXACT_BIN_PROBE_COUNT,
)
from cbase.bytemap.c_bytemap cimport (
    MIN_BYTEMAP_CAPACITY, DEFAULT_BYTEMAP_CAPACITY, BYTEMAP_GROWTH_FACTOR,
    MAX_BYTEMAP_CAPACITY, BYTEMAP_SALT_MAGIC,
)
from cbase.intern_string.c_intern_string cimport (
    ISTR_INITIAL_CAPACITY, FNV_OFFSET_BASIS, FNV_PRIME, ISTR_USE_BYTEMAP_BACKEND,
)


# -- Internal (mutable) dict, nested per submodule -------------------------
cdef dict _config_view = {
    # === allocator protocol ===
    'allocator_protocol': {
        'AP_ALLOC_VIGILANT':              AP_ALLOC_VIGILANT,
        'AP_ALLOC_MAGIC':                 AP_ALLOC_MAGIC,
        'AP_DEALLOC_MAGIC':               AP_DEALLOC_MAGIC,
        'AP_DECREF_AUTOFREE':             AP_DECREF_AUTOFREE,
        'AP_ALLOC_WITH_LOCK':             AP_ALLOC_WITH_LOCK,
        'AP_ALLOC_WITH_SHM':              AP_ALLOC_WITH_SHM,
        'AP_ALLOC_WITH_FREELIST':         AP_ALLOC_WITH_FREELIST,
    },

    # === heap allocator ===
    'heap': {
        'AP_HEAP_AUTOPAGE_CAPACITY':      AP_HEAP_AUTOPAGE_CAPACITY,
        'AP_HEAP_AUTOPAGE_CAPACITY_MAX':  AP_HEAP_AUTOPAGE_CAPACITY_MAX,
        'AP_HEAP_AUTOPAGE_ALIGNMENT':     AP_HEAP_AUTOPAGE_ALIGNMENT,
        'AP_HEAP_EXACT_BIN_COUNT':        AP_HEAP_EXACT_BIN_COUNT,
        'AP_HEAP_LARGE_BIN_COUNT':        AP_HEAP_LARGE_BIN_COUNT,
        'AP_HEAP_BIN_COUNT':              AP_HEAP_BIN_COUNT,
        'AP_HEAP_PAGE_EXTEND_MAX':        AP_HEAP_PAGE_EXTEND_MAX,
        'AP_HEAP_PAGE_FIT_TO_REQUEST':    AP_HEAP_PAGE_FIT_TO_REQUEST,
        'AP_HEAP_EXACT_BIN_PROBE_COUNT':  AP_HEAP_EXACT_BIN_PROBE_COUNT,
    },

    # === shared-memory allocator ===
    'shm': {
        'AP_SHM_AUTOPAGE_CAPACITY':             AP_SHM_AUTOPAGE_CAPACITY,
        'AP_SHM_AUTOPAGE_CAPACITY_MAX':         AP_SHM_AUTOPAGE_CAPACITY_MAX,
        'AP_SHM_AUTOPAGE_ALIGNMENT':            AP_SHM_AUTOPAGE_ALIGNMENT,
        'AP_SHM_ALLOCATOR_PREFIX':              AP_SHM_ALLOCATOR_PREFIX.decode() if isinstance(AP_SHM_ALLOCATOR_PREFIX, bytes) else AP_SHM_ALLOCATOR_PREFIX,
        'AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE': AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE,
        'AP_SHM_NAME_LEN':                      AP_SHM_NAME_LEN,
        'AP_SHM_PREFIX_MAX':                    AP_SHM_PREFIX_MAX,
        'AP_SHM_EXACT_BIN_COUNT':               AP_SHM_EXACT_BIN_COUNT,
        'AP_SHM_LARGE_BIN_COUNT':               AP_SHM_LARGE_BIN_COUNT,
        'AP_SHM_BIN_COUNT':                     AP_SHM_BIN_COUNT,
        'AP_SHM_PAGE_EXTEND_MAX':               AP_SHM_PAGE_EXTEND_MAX,
        'AP_SHM_PAGE_FIT_TO_REQUEST':           AP_SHM_PAGE_FIT_TO_REQUEST,
        'AP_SHM_EXACT_BIN_PROBE_COUNT':         AP_SHM_EXACT_BIN_PROBE_COUNT,
    },

    # === bytemap ===
    'bytemap': {
        'MIN_BYTEMAP_CAPACITY':           MIN_BYTEMAP_CAPACITY,
        'DEFAULT_BYTEMAP_CAPACITY':       DEFAULT_BYTEMAP_CAPACITY,
        'BYTEMAP_GROWTH_FACTOR':          BYTEMAP_GROWTH_FACTOR,
        'MAX_BYTEMAP_CAPACITY':           MAX_BYTEMAP_CAPACITY,
        'BYTEMAP_SALT_MAGIC':             BYTEMAP_SALT_MAGIC,
    },

    # === intern string ===
    'intern_string': {
        'ISTR_INITIAL_CAPACITY':          ISTR_INITIAL_CAPACITY,
        'ISTR_USE_BYTEMAP_BACKEND':       ISTR_USE_BYTEMAP_BACKEND,
        'FNV_OFFSET_BASIS':               FNV_OFFSET_BASIS,
        'FNV_PRIME':                      FNV_PRIME,
    },
}

# -- Public read-only view (nested proxies, immutable at every level) -----
from types import MappingProxyType
CONFIG_VIEW = MappingProxyType({
    name: MappingProxyType(section) for name, section in _config_view.items()
})
