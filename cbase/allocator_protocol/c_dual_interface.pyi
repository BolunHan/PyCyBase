from typing import Self


class CCPType:
    """Base class for Cython wrappers bound to an allocator-protocol buffer.

    Inheriting this class registers a wrapper with the underlying buffer's
    allocator protocol via ``ccp_bind`` / ``ccp_bind_embedded``, so the
    wrapper is automatically unbound and invalidated when the buffer is
    freed (the FREE pass). Subclasses must call ``ccp_bind`` after every
    ``_new``-like init and ``ccp_bind`` / ``ccp_bind_embedded`` after every
    ``c_from_header``-like adoption.

    Attributes:
        ap_header: **cython internal** Pointer to the bound `allocator_protocol`.
        ap_binding_id: **cython internal** Callback registration id.
        ap_header_offset: **cython internal** Byte offset of the subclass's header field.
        cy_extra_dealloc_fn: **cython internal** Armed ``__ccp_dealloc__`` override, if any.
    """

    @property
    def address(self) -> str:
        """Buffer address of the bound allocator protocol.

        Returns:
            The buffer address as a hex string, or ``'NULL'`` when unbound.
        """
        ...


class CCPBoundBuffer(CCPType):
    """An ap-allocated byte buffer bound to the allocator protocol.

    Supports all three binding scenarios: owned (fresh allocation), view
    (adopted block start, not owned), and embedded (interior pointer into a
    parent block). The buffer is treated as a NUL-terminated byte string:
    ``values`` returns the full size bytes (zero-padded on write), and
    adopted views derive their ``size`` via ``strlen``.

    Attributes:
        size: Buffer size in bytes; zeroed when the buffer is released.
        header: **cython internal** Pointer to the wrapped buffer.
        owner: **cython internal** Whether this instance owns the buffer.
    """

    size: int

    def __init__(self, size: int) -> None:
        """Initialize an owned buffer of the given size.

        Args:
            size: Buffer size in bytes.
        """
        ...

    def self_dealloc(self) -> Self:
        """Free the buffer immediately and invalidate every bound wrapper.

        Returns:
            The instance itself; afterwards the wrapper is unbound, its
            ``header`` is NULL and ``size`` is zeroed.
        """
        ...

    def alloc_child(self, size: int) -> CCPBoundBuffer:
        """Allocate a child block owned by this buffer.

        The child is an owned, bound buffer linked into this buffer's
        ownership tree; freeing this buffer with ``free_owned`` recursively
        frees the child (invalidating its wrapper).

        Args:
            size: Child buffer size in bytes.

        Returns:
            The new child buffer.

        Raises:
            BufferError: If this buffer was released.
            MemoryError: If the allocation failed.
        """
        ...

    def free_owned(self) -> None:
        """Free this buffer together with the whole ownership tree below it.

        Every bound wrapper of the tree is invalidated: ``header`` becomes
        NULL and ``size`` is zeroed. Idempotent on a released buffer.
        """
        ...

    @property
    def values(self) -> bytes | None:
        """The buffer content as bytes, zero-padded to the full size.

        Returns:
            The full-size byte string, or ``None`` when the buffer was
            released.
        """
        ...

    @values.setter
    def values(self, value: bytes) -> None:
        """Copy bytes into the buffer, truncating to ``size`` and zeroing
        the remainder.

        Args:
            value: Bytes to write.

        Raises:
            BufferError: If the buffer was released.
            RuntimeError: If ``value`` is empty.
        """
        ...


class CCPDualInterfaceTestToolkit:
    """Test toolkit exposing the cdef-only ``CCPBoundBuffer`` operations to
    Python, driving all three binding scenarios: owned, view (ap-allocated
    block start, not owned), and embedded (interior pointer into a parent
    block).
    """

    @staticmethod
    def c_from_header(header_addr: int, owner: bool = False) -> CCPBoundBuffer:
        """Adopt an existing buffer pointer as an unbound wrapper.

        Args:
            header_addr: Raw buffer pointer as an integer.
            owner: Whether the adopted wrapper owns the buffer.

        Returns:
            An unbound ``CCPBoundBuffer``; bind it with ``ccp_bind`` or
            ``ccp_bind_embedded``.
        """
        ...

    @staticmethod
    def ccp_bind(array: CCPBoundBuffer) -> None:
        """Bind a block-start wrapper to its buffer's protocol.

        Args:
            array: The wrapper to bind.
        """
        ...

    @staticmethod
    def ccp_bind_embedded(array: CCPBoundBuffer, parent_addr: int) -> None:
        """Bind an interior-pointer wrapper to a parent block.

        Args:
            array: The wrapper to bind.
            parent_addr: The parent block start as an integer.
        """
        ...

    @staticmethod
    def ccp_unbind(array: CCPBoundBuffer) -> None:
        """Release a wrapper's binding; idempotent when already unbound.

        Args:
            array: The wrapper to unbind.
        """
        ...

    @staticmethod
    def embedded_from(parent: CCPBoundBuffer, index: int) -> CCPBoundBuffer:
        """Create a bound embedded view of ``parent`` at the byte offset
        ``index``.

        Args:
            parent: The parent buffer wrapper.
            index: Byte offset into the parent buffer.

        Returns:
            A bound ``CCPBoundBuffer`` whose header points into the parent.

        Raises:
            BufferError: If the parent buffer was released.
            IndexError: If ``index`` is beyond the parent size.
        """
        ...

    @staticmethod
    def header_addr(array: CCPBoundBuffer) -> int:
        """The raw header pointer value of a wrapper.

        Args:
            array: The wrapper to inspect.

        Returns:
            The header pointer as an integer, 0 when NULL.
        """
        ...

    @staticmethod
    def alloc_child(parent: CCPBoundBuffer, size: int) -> CCPBoundBuffer:
        """Allocate a child block owned by ``parent``.

        Args:
            parent: The parent buffer.
            size: Child buffer size in bytes.

        Returns:
            The new bound, owned child buffer.

        Raises:
            BufferError: If ``parent`` was released.
            MemoryError: If the allocation failed.
        """
        ...

    @staticmethod
    def free_owned(array: CCPBoundBuffer) -> None:
        """Free ``array`` together with its whole ownership tree.

        Args:
            array: The buffer to free recursively.
        """
        ...

    @staticmethod
    def realloc_owned(array: CCPBoundBuffer, new_size: int) -> CCPBoundBuffer:
        """Reallocate a buffer — grows move the block, shrinks stay in place.

        Grow: ``array`` is invalidated in place (header NULL, size 0) and the
        returned wrapper owns the moved block carrying the same hierarchy.
        Shrink: the block is not recycled — only the header size changes,
        the SAME wrapper is returned (and a warning is logged).
        ``new_size == 0`` logs an error and aborts.

        Args:
            array: The buffer to reallocate (must be a block start).
            new_size: New buffer size in bytes (must be > 0).

        Returns:
            The wrapper of the (possibly moved) block — ``array`` itself on
            shrink.

        Raises:
            BufferError: If ``array`` was released.
            MemoryError: If the reallocation failed.
        """
        ...

    @staticmethod
    def hierarchy_addr(array: CCPBoundBuffer) -> tuple[int, int, int, int]:
        """The ownership tree pointers of a block-start buffer.

        Args:
            array: The buffer to inspect (must be a block start).

        Returns:
            A ``(parent, first_child, next_sibling, prev_sibling)`` tuple of
            raw protocol addresses; 0 means NULL. The parent slot is 0 for
            roots.

        Raises:
            BufferError: If ``array`` was released.
        """
        ...

    @staticmethod
    def protocol_addr(array: CCPBoundBuffer) -> int:
        """The raw protocol header address of a block-start buffer.

        Args:
            array: The buffer to inspect (must be a block start).

        Returns:
            The allocator protocol address as an integer.

        Raises:
            BufferError: If ``array`` was released.
        """
        ...

    @staticmethod
    def raw_free(array: CCPBoundBuffer) -> None:
        """Call ``c_ap_free`` directly, bypassing ``free_owned``.

        Test-only: freeing a buffer that still owns children with this
        aborts under ``AP_ALLOC_VIGILANT``.

        Args:
            array: The buffer to free non-recursively.
        """
        ...

    @staticmethod
    def acquire_ownership(array: CCPBoundBuffer, new_parent_addr: int = 0) -> None:
        """Acquire ownership of a buffer — detach it or re-parent it.

        With ``new_parent_addr == 0`` the buffer (together with its own
        children) is detached from its tree and becomes an independent
        root; idempotent on roots. With a parent address given, the buffer
        and its subtree are moved under the new parent (pushed at the head
        of its child list). The refcount is not touched.

        Args:
            array: The buffer to acquire (must be a block start).
            new_parent_addr: Raw header address of the new parent buffer;
                0 detaches instead. A buffer cannot be parented under
                itself or its own descendant (VIGILANT abort).

        Raises:
            BufferError: If ``array`` was released.
        """
        ...
