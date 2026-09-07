from typing import Self


class CCPType:
    """Base class for Cython wrappers bound to an allocator-protocol buffer.

    Inheriting this class registers a wrapper with the underlying buffer's
    allocator protocol via ``ccp_bind`` / ``ccp_bind_embedded``, so the
    wrapper is automatically unbound and invalidated when the buffer is
    freed (the DEALLOC pass). Subclasses must call ``ccp_bind`` after every
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
