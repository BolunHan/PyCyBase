import sys

from .c_heap_allocator import (
    ALLOCATOR as HEAP_ALLOCATOR,
    HeapAllocator,
    HeapMemoryBlock,
    HeapMemoryPage
)

if sys.platform == "win32":
    from .c_nt_shm_allocator import (
        NtSharedMemoryAllocator,
    )
    SHM_ALLOCATOR = None
    SharedMemoryAllocator = NtSharedMemoryAllocator  # alias for compat
    SharedMemoryBlock = None  # not implemented in NT wrapper
    SharedMemoryPage = None   # not implemented in NT wrapper
    def shm_cleanup():
        pass
else:
    from .c_shm_allocator import (
        ALLOCATOR as SHM_ALLOCATOR,
        SharedMemoryAllocator,
        SharedMemoryBlock,
        SharedMemoryPage,
        cleanup as shm_cleanup
    )

from .c_allocator_protocol import (
    AllocatorProtocol,
    AP_FREELIST,
    AP_LOCKED,
    AP_LOCKFREE,
    AP_SHARED,
    AllocatorConfigContext,
)

__all__ = [
    'HEAP_ALLOCATOR', 'HeapAllocator', 'HeapMemoryBlock', 'HeapMemoryPage',
    'SHM_ALLOCATOR', 'SharedMemoryAllocator', 'SharedMemoryBlock', 'SharedMemoryPage', 'shm_cleanup',
    'AllocatorProtocol', 'AP_FREELIST', 'AP_LOCKED', 'AP_LOCKFREE', 'AP_SHARED', 'AllocatorConfigContext'
]

if sys.platform == "win32":
    __all__.append('NtSharedMemoryAllocator')
