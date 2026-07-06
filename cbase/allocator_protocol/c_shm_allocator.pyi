"""POSIX shared-memory backed allocator

This module provides a Python wrapper around a C-backed shared memory allocator.

The allocator:
- Is backed by POSIX shared memory (shm). It creates named shm objects
  and maps them into a reserved virtual address region so multiple
  processes can agree on fixed addresses for mapped pages.
- Requests a fixed virtual address region so pages can be mapped at
  stable addresses across processes (this enables multi-process access
  to the same in-region pointers).
- By default reserves a ``128 GiB`` virtual address space for page
  mappings (``AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE``).
- Is POSIX-only (depends on shm_open/mmap semantics available on POSIX
  systems such as Linux).

Compile-time constants
----------------------
These values are provided by the C header and may be changed at
compile time when building the extension. The runtime values come from
the compiled extension.

- ``AP_SHM_AUTOPAGE_CAPACITY``: 64 * 1024        # 64 KiB — first/auto page size
- ``AP_SHM_AUTOPAGE_CAPACITY_MAX``: 16 * 1024 * 1024  # 16 MiB — maximum page
- ``AP_SHM_AUTOPAGE_ALIGNMENT``: 4 * 1024         # 4 KiB — page alignment
- ``AP_SHM_ALLOCATOR_PREFIX``: ``"/c_cbase_shm"``  # default SHM prefix
- ``AP_SHM_NAME_LEN``: 256                         # max SHM name length
- ``AP_SHM_PREFIX_MAX``: 64                        # max custom prefix length
- ``AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE``: 128 << 30  # 128 GiB

Naming convention
-----------------
Allocator SHM objects use the suffix ``_ac`` (e.g. ``/c_cbase_shm_ac_3e8_7f...``).
Page SHM objects use the suffix ``_pg`` (e.g. ``/c_cbase_shm_pg_3e8_000000``).
"""
import ctypes
from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated


@dataclass
class ValueRange:
    lo: int
    hi: int


UINTPTR_MAX = ctypes.c_void_p(-1).value
uintptr_t = Annotated[int, ValueRange(0, UINTPTR_MAX), ctypes.c_void_p]


class SharedMemoryBlock:
    """Represents an allocated block inside a shared memory page."""

    owner: bool

    def __init__(self, block: uintptr_t = 0, owner: bool = False) -> None: ...

    def __repr__(self) -> str: ...

    @property
    def size(self) -> int:
        """Requested payload size in bytes (-1 if uninitialized, 0 if freed)."""

    @property
    def capacity(self) -> int:
        """Aligned capacity of the block (-1 if uninitialized)."""

    @property
    def next_free(self) -> SharedMemoryBlock | None:
        """Next entry in the allocator free list, if any."""

    @property
    def next_allocated(self) -> SharedMemoryBlock | None:
        """Next entry in the page's allocation list, if any."""

    @property
    def buffer(self) -> memoryview | None:
        """Memoryview of the user buffer (None if uninitialized or zero-sized)."""

    @property
    def address(self) -> str | None:
        """Hex string of the buffer address."""

    @property
    def page_address(self) -> str | None:
        """Hex string of the parent page's base address."""


class SharedMemoryPage:
    """Represents a mapped shared-memory page."""

    def __init__(self, page_addr: uintptr_t = 0) -> None: ...

    def __repr__(self) -> str: ...

    def __bool__(self) -> bool: ...

    @classmethod
    def from_buffer(cls, buffer_addr: uintptr_t) -> SharedMemoryPage:
        """Reconstruct a page wrapper from a buffer address within it."""

    def allocated(self) -> Generator[SharedMemoryBlock, None, None]:
        """Iterate allocated blocks newest-first."""

    def reclaim(self) -> None:
        """Best-effort reclaim of freed blocks back to unused space."""

    @property
    def name(self) -> str | None:
        """The OS shared-memory object name for this page."""

    @property
    def capacity(self) -> int:
        """Total capacity of the page in bytes (0 if uninitialized)."""

    @property
    def occupied(self) -> int:
        """Currently occupied bytes on the page (0 if uninitialized)."""

    @property
    def address(self) -> str | None:
        """Hex string of the page's base address."""


class SharedMemoryAllocator:
    """Top-level allocator managing a large virtual region and multiple pages.

    Typical usage::

        >>> alloc = SharedMemoryAllocator()
        >>> page = alloc.extend()
        >>> block = alloc.calloc(1024)
        >>> alloc.free(block)
        >>> alloc.reclaim()
    """

    owner: bool

    def __init__(self, region_size: int = 0, shm_prefix: str | None = None) -> None:
        """Create and initialize an allocator context.

        Args:
            region_size: Virtual region size to reserve (0 for default 128 GiB).
            shm_prefix: Custom SHM name prefix (None for ``AP_SHM_ALLOCATOR_PREFIX``).

        Raises:
            OSError: If the underlying C allocator cannot be created.
        """

    def __repr__(self) -> str: ...

    @classmethod
    def get_pid(cls, shm_name: str) -> int:
        """Extract the creator PID from an allocator or page SHM name.

        Args:
            shm_name: SHM object name (with leading '/').

        Returns:
            PID on success, -1 on parse failure.
        """

    def extend(self, capacity: int = 0, with_lock: bool = True) -> SharedMemoryPage:
        """Add a page (auto-sized when capacity is 0).

        Raises:
            OSError: On mapping/allocation failure.
        """

    def calloc(self, size: int, with_lock: bool = True) -> SharedMemoryBlock:
        """Allocate zeroed memory from the active page (auto-extending).

        Raises:
            OSError: On allocation failure.
        """

    def request(
            self,
            size: int,
            scan_all_pages: bool = True,
            with_lock: bool = True,
    ) -> SharedMemoryBlock:
        """Request a zeroed block, scanning free list then pages.

        Raises:
            OSError: On allocation failure.
        """

    def free(self, buffer: SharedMemoryBlock, with_lock: bool = True) -> None:
        """Return a block to the allocator free list."""

    def reclaim(self, with_lock: bool = True) -> None:
        """Reclaim freed space across all pages."""

    def dangling(self, shm_prefix: str | None = None) -> list[str]:
        """Return allocator SHM names whose creator PID is gone.

        Args:
            shm_prefix: Prefix to scan for (None for default, appends ``_ac``).
        """

    def dangling_pages(self, shm_prefix: str | None = None) -> list[str]:
        """Return page SHM names whose creator PID is gone.

        Args:
            shm_prefix: Prefix to scan for (None for default, appends ``_pg``).
        """

    def cleanup_dangling(self, shm_prefix: str | None = None) -> None:
        """Unlink dangling allocator and page SHM objects.

        Args:
            shm_prefix: Prefix to scan for (None for default).
        """

    def pages(self) -> Generator[SharedMemoryPage, None, None]:
        """Iterate mapped pages newest-first."""

    def allocated(self) -> Generator[SharedMemoryBlock, None, None]:
        """Iterate allocated blocks across all pages."""

    def free_list(self) -> Generator[SharedMemoryBlock, None, None]:
        """Iterate the allocator-wide free list."""

    # -- metadata properties --

    @property
    def name(self) -> str | None:
        """The allocator SHM object name (with leading '/')."""

    @property
    def pid(self) -> int:
        """PID of the process that created the allocator (-1 if unknown)."""

    @property
    def region(self) -> int:
        """Base virtual address of the reserved region (-1 if uninitialized)."""

    @property
    def region_addr(self) -> str | None:
        """Base virtual address as hex string."""

    @property
    def region_size(self) -> int:
        """Virtual region size in bytes (-1 if uninitialized)."""

    @property
    def mapped_size(self) -> int:
        """Total mapped bytes within the region (-1 if uninitialized)."""

    @property
    def mapped_pages(self) -> int:
        """Number of pages currently mapped (-1 if uninitialized)."""

    @property
    def active_page(self) -> SharedMemoryPage | None:
        """Most recently mapped page, or None."""

    # -- config properties (read/write) --

    @property
    def autopage_capacity(self) -> int:
        """Default capacity for auto-sized pages."""

    @autopage_capacity.setter
    def autopage_capacity(self, value: int) -> None: ...

    @property
    def autopage_capacity_max(self) -> int:
        """Maximum capacity a page can grow to."""

    @autopage_capacity_max.setter
    def autopage_capacity_max(self, value: int) -> None: ...

    @property
    def autopage_alignment(self) -> int:
        """Page alignment in bytes."""

    @autopage_alignment.setter
    def autopage_alignment(self, value: int) -> None: ...

    @property
    def shm_prefix(self) -> str | None:
        """The SHM prefix used by this allocator instance."""


# Module-level exports

ALLOCATOR: SharedMemoryAllocator | None
"""Global singleton allocator instance."""

AP_SHM_AUTOPAGE_CAPACITY: int
AP_SHM_AUTOPAGE_CAPACITY_MAX: int
AP_SHM_AUTOPAGE_ALIGNMENT: int
AP_SHM_ALLOCATOR_PREFIX: str
AP_SHM_NAME_LEN: int
AP_SHM_PREFIX_MAX: int
AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE: int
