from .c_allocator_protocol cimport (
    AP_ALLOC_VIGILANT, AP_ALLOC_MAGIC,

    allocator_protocol,
    c_ap_allocator_protocol_new,
    c_ap_allocator_protocol_free,
    c_ap_allocator_protocol_acquire_owner,
    c_ap_allocator_protocol_release_owner,

    c_ap_protocol_from_ptr,
    c_ap_alloc,
    c_ap_free,
    c_ap_incref,
    c_ap_decref,
    c_ap_strdup,
    c_ap_realloc,
    c_ap_is_allocator_buf,

    AP_ALLOC_WITH_LOCK, AP_ALLOC_WITH_SHM, AP_ALLOC_WITH_FREELIST,
    EnvConfigContext, AllocatorConfigContext,
    AP_SHARED, AP_LOCKED, AP_LOCKFREE, AP_FREELIST,
    AllocatorProtocol,
    AP_DEFAULT_ALLOCATOR, AP_SHM_ALLOCATOR, AP_HEAP_ALLOCATOR
)

from .c_heap_allocator cimport (
    AP_HEAP_AUTOPAGE_CAPACITY, AP_HEAP_AUTOPAGE_CAPACITY_MAX, AP_HEAP_AUTOPAGE_ALIGNMENT,
    AP_HEAP_EXACT_BIN_COUNT, AP_HEAP_LARGE_BIN_COUNT, AP_HEAP_BIN_COUNT,
    AP_HEAP_PAGE_EXTEND_MAX, AP_HEAP_PAGE_FIT_TO_REQUEST, AP_HEAP_EXACT_BIN_PROBE_COUNT,

    heap_memory_block, heap_page, heap_allocator,
    c_heap_page_roundup,
    c_heap_block_roundup,
    c_heap_block_ceil_log2,
    c_heap_block_bin,
    c_heap_page_reclaim,

    c_heap_allocator_extend,
    c_heap_allocator_new,
    c_heap_allocator_free,
    c_heap_calloc,
    c_heap_request,
    c_heap_free,
    c_heap_reclaim,

    HeapMemoryPage, HeapMemoryBlock, HeapAllocator, ALLOCATOR as HEAP_ALLOCATOR, C_ALLOCATOR as C_HEAP_ALLOCATOR
)

from .c_shm_comp cimport (
    AP_SHM_AUTOPAGE_CAPACITY, AP_SHM_AUTOPAGE_CAPACITY_MAX, AP_SHM_AUTOPAGE_ALIGNMENT, AP_SHM_ALLOCATOR_PREFIX, AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE,
    AP_SHM_EXACT_BIN_COUNT, AP_SHM_LARGE_BIN_COUNT, AP_SHM_BIN_COUNT,
    AP_SHM_PAGE_EXTEND_MAX, AP_SHM_PAGE_FIT_TO_REQUEST, AP_SHM_EXACT_BIN_PROBE_COUNT,

    shm_allocator, shm_allocator_ctx,

    c_shm_allocator_new,
    c_shm_allocator_free,
    c_shm_calloc,
    c_shm_request,
    c_shm_free,
    c_shm_reclaim,

    C_SHM_COMP
)
