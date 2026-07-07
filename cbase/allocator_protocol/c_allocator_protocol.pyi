from typing import Any

from cbase.env import EnvConfigContext


class AllocatorConfigContext(EnvConfigContext):
    """Context manager that extends EnvConfigContext to also dispatch config
    changes to the underlying heap and shared-memory allocators.

    Accepted keyword arguments (in addition to those inherited):

    * ``locked: bool`` — enable/disable mutex locking
    * ``shared: bool`` — enable/disable shared memory
    * ``freelist: bool`` — enable/disable free list
    * ``autopage_capacity: int`` — propagated to both heap and SHM allocators
    * ``autopage_capacity_max: int`` — propagated to both heap and SHM allocators
    * ``autopage_alignment: int`` — propagated to both heap and SHM allocators
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize the context with configuration changes.

        Args:
            **kwargs: Configuration key-value pairs to set temporarily
        """
        ...

    def __or__(self, other: AllocatorConfigContext) -> AllocatorConfigContext:
        """
        Combine two AllocatorConfigContext instances.

        Args:
            other: Another AllocatorConfigContext instance

        Returns:
            A new AllocatorConfigContext with combined configurations
        """
        ...

    def __invert__(self) -> AllocatorConfigContext:
        """
        Invert the AllocatorConfigContext.

        Returns:
            A new AllocatorConfigContext that reverts the configurations.
        """
        ...


AP_SHARED: AllocatorConfigContext
"""
AllocatorConfigContext instance to set flag for cbase to use SHM allocator.
"""

AP_LOCKED: AllocatorConfigContext
"""
AllocatorConfigContext instance to set flag for cbase to use thread safe mode.
"""

AP_LOCKFREE: AllocatorConfigContext
"""
AllocatorConfigContext instance to set flag for cbase to disable thread safe mode.
"""

AP_FREELIST: AllocatorConfigContext
"""
AllocatorConfigContext instance to set flag for cbase to use freelist. Have no effect when in AP_SHARED mode, which enforces its own free list.
"""


class AllocatorProtocol:
    """Protocol for memory allocation with environment-based configuration.

    Manages an underlying `allocator_protocol` C structure, handling memory
    allocation and deallocation based on global environment settings.

    Attributes:
        protocol: **cython internal** Pointer to the underlying `allocator_protocol` C structure.
        owner: **cython internal** Boolean indicating if this instance owns the protocol and is
            responsible for its deallocation.
    """

    def __init__(self, size: int) -> None:
        """Initialize the AllocatorProtocol with a specified buffer size.

        Args:
            size: The size of the buffer to allocate in bytes.
        """
        ...

    @property
    def buf(self) -> memoryview:
        """Memory buffer managed by this allocator protocol.

        Returns:
            A memoryview representing the allocated buffer.
        """
        ...

    @property
    def size(self) -> int:
        """Size of the allocated buffer.

        Returns:
            The size of the buffer in bytes.
        """
        ...

    @property
    def with_shm(self) -> bool:
        """Indicates if the allocator uses shared memory.

        Returns:
            True if shared memory is used, False otherwise.
        """
        ...

    @property
    def with_lock(self) -> bool:
        """Indicates if the allocator uses locking for thread safety.

        Returns:
            True if locking is enabled, False otherwise.
        """
        ...

    @property
    def with_freelist(self) -> bool:
        """Indicates if the allocator uses a free list.

        Returns:
            True if free list is enabled, False otherwise.
        """
        ...

    @property
    def addr(self) -> int:
        """Memory address of the underlying allocator protocol structure.

        Returns:
            The memory address as an integer.
        """
        ...
