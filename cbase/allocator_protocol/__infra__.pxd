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

    AP_ALLOC_WITH_LOCK, AP_ALLOC_WITH_SHM, AP_ALLOC_WITH_FREELIST,
    EnvConfigContext, AllocatorConfigContext,
    AP_SHARED, AP_LOCKED, AP_LOCKFREE, AP_FREELIST,
    AllocatorProtocol,
    AP_DEFAULT_ALLOCATOR, AP_SHM_ALLOCATOR, AP_HEAP_ALLOCATOR
)

from .c_heap_allocator cimport (
    AP_HEAP_AUTOPAGE_CAPACITY, AP_HEAP_AUTOPAGE_CAPACITY_MAX, AP_HEAP_AUTOPAGE_ALIGNMENT,

    heap_memory_block, heap_page, heap_allocator,
    c_heap_page_roundup,
    c_heap_block_roundup,
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

IF UNAME_SYSNAME == "Windows":
    from .c_nt_shm_allocator cimport (
        AP_SHM_AUTOPAGE_CAPACITY, AP_SHM_AUTOPAGE_CAPACITY_MAX, AP_SHM_AUTOPAGE_ALIGNMENT, AP_SHM_ALLOCATOR_PREFIX, AP_SHM_NAME_LEN, AP_SHM_PREFIX_MAX, AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE, c_nt_shm_page_overhead, c_nt_shm_block_overhead,

        nt_shm_page, nt_shm_page_ctx, nt_shm_memory_block, nt_shm_allocator, nt_shm_allocator_ctx,
        c_nt_shm_page_roundup,
        c_nt_shm_block_roundup,
        c_nt_shm_allocator_name,
        c_nt_shm_page_name,
        c_nt_shm_mutex_name,
        c_nt_shm_scan,
        c_nt_shm_page_new,
        c_nt_shm_page_map,
        c_nt_shm_page_reclaim,

        c_nt_shm_allocator_extend,
        c_nt_shm_allocator_new,
        c_nt_shm_allocator_free,
        c_nt_shm_calloc,
        c_nt_shm_request,
        c_nt_shm_free,
        c_nt_shm_reclaim,
        c_nt_shm_scan_allocator,
        c_nt_shm_scan_page,
        c_nt_shm_pid,
        c_nt_shm_allocator_dangling,
        c_nt_shm_clear_dangling,

        NtSharedMemoryAllocator,
    )
ELSE:
    from .c_shm_allocator cimport (
        AP_SHM_AUTOPAGE_CAPACITY, AP_SHM_AUTOPAGE_CAPACITY_MAX, AP_SHM_AUTOPAGE_ALIGNMENT, AP_SHM_ALLOCATOR_PREFIX, AP_SHM_NAME_LEN, AP_SHM_PREFIX_MAX, AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE, c_shm_page_overhead, c_shm_block_overhead,

        shm_page, shm_page_ctx, shm_memory_block, shm_allocator, shm_allocator_ctx,
        c_shm_page_roundup,
        c_shm_block_roundup,
        c_shm_allocator_name,
        c_shm_page_name,
        c_shm_scan,
        c_shm_page_new,
        c_shm_page_map,
        c_shm_page_reclaim,

        c_shm_allocator_extend,
        c_shm_allocator_new,
        c_shm_allocator_free,
        c_shm_calloc,
        c_shm_request,
        c_shm_free,
        c_shm_reclaim,
        c_shm_scan_allocator,
        c_shm_scan_page,
        c_shm_pid,
        c_shm_allocator_dangling,
        c_shm_clear_dangling,

        SharedMemoryPage, SharedMemoryBlock, SharedMemoryAllocator, ALLOCATOR as SHM_ALLOCATOR, C_ALLOCATOR as C_SHM_ALLOCATOR
    )
