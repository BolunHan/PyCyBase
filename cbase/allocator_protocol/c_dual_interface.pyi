from ctypes import POINTER, c_void_p
from typing import Annotated, Self

# Type-hint-only helpers for the raw C pointer arguments of the internal
# cdef binding methods — defined here, never imported elsewhere.
c_void_ptr = Annotated[int, c_void_p]  # const void* — block pointers
c_void_ptr_ptr = Annotated[int, POINTER(c_void_p)]  # const void** — address of the header field


class CCPType:
    """Base class for Cython wrappers bound to an allocator-protocol buffer.

    Inheriting this class registers a wrapper with the underlying buffer's
    allocator protocol via ``ccp_bind`` / ``ccp_bind_embedded``, so the
    wrapper is automatically unbound and invalidated when the buffer is
    freed (the FREE pass). Subclasses must call ``ccp_bind`` after every
    ``_new``-like init and ``ccp_bind`` / ``ccp_bind_embedded`` after
    every ``c_from_header``-like adoption. For wrappers that CANNOT
    inherit ``CCPType`` (e.g. dict-derived classes like ``BoundByteMap``),
    use the attachment protocol instead — see ``CCPAttachedBuffer``.

    Attributes:
        ap_header: **cython internal** Pointer to the bound `allocator_protocol`.
        ap_binding_id: **cython internal** Callback registration id.
        ccp_header_offset: **cython internal** Byte offset of the subclass's header field.
        ccp_ctx_offset: **cython internal** Part of the shared ccp_ctx layout; always 0 for the bound variant (only the attached variant stores its ccp_ctx field offset there).
        cy_extra_dealloc_fn: **cython internal** Armed ``__ccp_dealloc__`` override, if any.

    The internal cdef binding methods (``__ccp_dealloc__``, ``ccp_bind``,
    ``ccp_bind_embedded``, ``ccp_unbind``) and the static attachment
    helpers (``c_attach``, ``c_attach_embedded``, ``c_detach``) are
    documented below as a deliberate exception — CCPType is foundational
    infrastructure; they are **not callable from Python** (the static
    helpers are cimport-callable from Cython modules).
    """

    @property
    def address(self) -> str:
        """Buffer address of the bound allocator protocol.

        Returns:
            The buffer address as a hex string, or ``'NULL'`` when unbound.
        """
        ...

    # -- cython internal cdef methods (documented exception) ---------------

    def __ccp_dealloc__(self) -> None:
        """**cython internal** Extra-teardown hook fired by the FREE pass.

        A ``cdef`` override runs when the bound/attached buffer is freed,
        BEFORE the wrapper's header field is nulled — so the header may
        still be dereferenced (e.g. zero a derived size). The base
        implementation is a no-op; an override is detected automatically
        at bind/attach time and armed into ``cy_extra_dealloc_fn``.
        Overrides must not raise: they run inside the C FREE pass.
        """
        ...

    def ccp_bind(self, c_header: c_void_ptr_ptr) -> None:
        """**cython internal** Bind this wrapper to a block-start buffer.

        Registers the wrapper on the buffer's allocator protocol, so the
        FREE pass unbinds it and nulls its header field before the block
        is reclaimed. Call after every ``_new``-like init and every
        block-start adoption (``c_from_header`` never binds itself).

        Signature as void* c_header as intended, only in this way the cython can skip the otherwise enforced type check.

        Args:
            c_header: Address of the wrapper's header field
                (``&self.header``) — a ``void**`` slot; the field must
                hold a block-start buffer pointer, not an interior
                pointer (use ``ccp_bind_embedded`` for those).

        Raises:
            BufferError: If the binding could not be registered (e.g. the
                header is NULL).
        """
        ...

    def ccp_bind_embedded(self, c_header: c_void_ptr_ptr, parent_header: c_void_ptr) -> None:
        """**cython internal** Bind an interior-pointer header to a parent block.

        Like ``ccp_bind``, but the protocol and the held reference are
        derived from ``parent_header`` — the parent BLOCK START — because
        no protocol can be derived from an interior pointer.

        Args:
            c_header: Address of the wrapper's header field
                (``&self.header``) — a ``void**`` slot; the field holds
                an interior pointer into the parent block.
            parent_header: The parent block start (``const void*``).

        Raises:
            BufferError: If the binding could not be registered.
        """
        ...

    def ccp_unbind(self) -> None:
        """**cython internal** Release the binding; idempotent.

        Unregisters the wrapper's callback, clears the binding state and
        releases the reference held on the block start. Already-unbound
        wrappers return silently — the post-free (husk) contract relies
        on this, and ``__dealloc__`` calls it unconditionally.

        Raises:
            BufferError: If the callback could not be unregistered.
        """
        ...

    @staticmethod
    def c_attach(py_object: c_void_ptr, c_header: c_void_ptr_ptr, ccp: c_void_ptr, dealloc_fn: c_void_ptr) -> None:
        """**cython internal** Attach an embedded ccp_ctx to a block-start buffer.

        The shared implementation of the attachment protocol: registers
        the ctx on the buffer's allocator protocol (the FREE pass then
        detaches the wrapper and nulls its header field) and arms
        ``dealloc_fn`` as the ``cy_extra_dealloc_fn`` hook. A
        cimport-callable static helper — attached wrapper classes
        delegate their own ``c_attach`` to this.

        Args:
            py_object: The wrapper object.
            c_header: Address of the wrapper's header field
                (``&self.header``) — a ``void**`` slot holding a
                block-start buffer pointer.
            ccp: Address of the wrapper's embedded ccp_ctx value field.
            dealloc_fn: The ``__ccp_dealloc__`` hook as a C function
                pointer address (``<void*> self.__ccp_dealloc__``).

        Raises:
            BufferError: If the attachment could not be registered (e.g.
                the header is NULL).
        """
        ...

    @staticmethod
    def c_attach_embedded(py_object: c_void_ptr, c_header: c_void_ptr_ptr, ccp: c_void_ptr, parent_header: c_void_ptr, dealloc_fn: c_void_ptr) -> None:
        """**cython internal** Attach an interior-pointer header to a parent block.

        The shared embedded variant: the protocol and the held reference
        are derived from ``parent_header`` — the parent BLOCK START.
        Cimport-callable static helper.

        Args:
            py_object: The wrapper object.
            c_header: Address of the wrapper's header field
                (``&self.header``) — a ``void**`` slot holding an
                interior pointer into the parent block.
            ccp: Address of the wrapper's embedded ccp_ctx value field.
            parent_header: The parent block start (``const void*``).
            dealloc_fn: The ``__ccp_dealloc__`` hook as a C function
                pointer address.

        Raises:
            BufferError: If the attachment could not be registered.
        """
        ...

    @staticmethod
    def c_detach(py_object: c_void_ptr, ccp: c_void_ptr) -> None:
        """**cython internal** Release an attachment; idempotent.

        Unregisters the ctx's callback, clears the binding state and
        releases the reference held on the block start. Cimport-callable
        static helper — attached wrapper classes delegate their own
        ``c_detach`` (called from ``__dealloc__``) to this.

        Args:
            py_object: The wrapper object.
            ccp: Address of the wrapper's embedded ccp_ctx value field.

        Raises:
            BufferError: If the callback could not be unregistered.
        """
        ...


class BoundBuffer:
    """An ap-allocated byte buffer WITHOUT allocator-protocol binding.

    The plain c-dual-interface design: the buffer is managed through the
    owner flag only — there is no reverse dealloc invalidation. A view
    adopted via ``c_from_header`` is a raw pointer; freeing the owner does
    NOT null the view's header (see ``CCPAttachedBuffer`` and
    ``CCPBoundBuffer`` for the CCP
    binding variants). The buffer is treated as a NUL-terminated byte
    string: ``values`` returns the full size bytes (zero-padded on write),
    and adopted views derive their ``size`` via ``strlen``.

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

    def alloc_child(self, size: int) -> BoundBuffer:
        """Allocate a child block owned by this buffer.

        The child is an owned buffer linked into this buffer's ownership
        tree; freeing this buffer with ``free_owned`` recursively frees the
        child.

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

        Idempotent on a released buffer.
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


class CCPAttachedBuffer(BoundBuffer):
    """A BoundBuffer bound through the CCP attachment protocol.

    The attachment protocol gives reverse dealloc invalidation to ANY
    c-dual-interface class without inheriting ``CCPType`` — which is
    impossible for classes that already have a layout base (e.g.
    dict-derived wrappers like ``BoundByteMap``, where Cython rejects a
    second extension-type base). Usage pattern:

    1. Define the class as a normal c-dual-interface design (here:
       ``BoundBuffer`` — header/owner pair, owner-flag freeing).
    2. Subclass it and embed the binding state (``cdef ccp_ctx ccp_ctx``);
       the repetitive protocol logic is bundled on ``CCPType`` as
       cimport-callable static helpers — ``CCPType.c_attach`` /
       ``CCPType.c_attach_embedded`` / ``CCPType.c_detach`` — and the
       class delegates to them from its own thin ``c_attach`` /
       ``c_attach_embedded`` / ``c_detach`` methods (one line each),
       detaching in ``__dealloc__``.
    3. Implement the class-specific glue: a ``__ccp_dealloc__`` hook
       (required by the protocol — a no-op body is valid), ``__init__``
       (attach after the ``_new``-like init), and ``c_from_header`` /
       ``c_alloc_child`` (attach at the adoption call sites, zeroing the
       ctx on ``__new__``-only paths).
    4. When the buffer is freed, the FREE pass detaches the wrapper, runs
       the armed ``__ccp_dealloc__`` hook (zeroes ``size``), and nulls
       the header before the block is reclaimed.

    The buffer is treated as a NUL-terminated byte string: ``values``
    returns the full size bytes (zero-padded on write), and adopted
    views derive their ``size`` via ``strlen``.

    Attributes:
        size: Buffer size in bytes; zeroed when the buffer is released.
        header: **cython internal** Pointer to the wrapped buffer.
        owner: **cython internal** Whether this instance owns the buffer.
        ccp_ctx: **cython internal** Embedded attachment binding state.
    """

    size: int

    def __init__(self, size: int) -> None:
        """Initialize an owned, attached buffer of the given size.

        Args:
            size: Buffer size in bytes.
        """
        ...

    def alloc_child(self, size: int) -> CCPAttachedBuffer:
        """Allocate an attached child block owned by this buffer.

        The child is an owned, attached buffer linked into this buffer's
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

    @property
    def address(self) -> str:
        """Buffer address of the attached allocator protocol.

        Returns:
            The buffer address as a hex string, or ``'NULL'`` when
            detached.
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
    """Test toolkit exposing the cdef-only dual-interface operations to
    Python, driving the bound scenarios (owned, view, embedded), the plain
    ``BoundBuffer`` design, and the ``CCPAttachedBuffer`` attachment
    protocol.
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
    def buffer_c_from_header(header_addr: int, owner: bool = False) -> BoundBuffer:
        """Adopt an existing buffer pointer as a plain ``BoundBuffer``.

        Args:
            header_addr: Raw buffer pointer as an integer.
            owner: Whether the adopted wrapper owns the buffer.

        Returns:
            A ``BoundBuffer`` without any allocator-protocol binding.
        """
        ...

    @staticmethod
    def buffer_header_addr(array: BoundBuffer) -> int:
        """The raw header pointer value of a plain ``BoundBuffer``.

        Args:
            array: The wrapper to inspect.

        Returns:
            The header pointer as an integer, 0 when NULL.
        """
        ...

    @staticmethod
    def buffer_alloc_child(parent: BoundBuffer, size: int) -> BoundBuffer:
        """Allocate a child block owned by ``parent``.

        Args:
            parent: The parent buffer.
            size: Child buffer size in bytes.

        Returns:
            The new child buffer.

        Raises:
            BufferError: If ``parent`` was released.
            MemoryError: If the allocation failed.
        """
        ...

    @staticmethod
    def buffer_free_owned(array: BoundBuffer) -> None:
        """Free ``array`` together with its whole ownership tree.

        Args:
            array: The buffer to free recursively.
        """
        ...

    @staticmethod
    def attached_c_from_header(header_addr: int, owner: bool = False) -> CCPAttachedBuffer:
        """Adopt an existing buffer pointer as an unattached
        ``CCPAttachedBuffer``.

        Args:
            header_addr: Raw buffer pointer as an integer.
            owner: Whether the adopted wrapper owns the buffer.

        Returns:
            An unattached ``CCPAttachedBuffer``; attach it with
            ``attached_attach`` or ``attached_attach_embedded``.
        """
        ...

    @staticmethod
    def attached_attach(array: CCPAttachedBuffer) -> None:
        """Attach a block-start wrapper to its buffer's protocol.

        Args:
            array: The wrapper to attach.
        """
        ...

    @staticmethod
    def attached_attach_embedded(array: CCPAttachedBuffer, parent_addr: int) -> None:
        """Attach an interior-pointer wrapper to a parent block.

        Args:
            array: The wrapper to attach.
            parent_addr: The parent block start as an integer.
        """
        ...

    @staticmethod
    def attached_detach(array: CCPAttachedBuffer) -> None:
        """Release a wrapper's attachment; idempotent when already detached.

        Args:
            array: The wrapper to detach.
        """
        ...

    @staticmethod
    def attached_embedded_from(parent: CCPAttachedBuffer, index: int) -> CCPAttachedBuffer:
        """Create an attached embedded view of ``parent`` at the byte offset
        ``index``.

        Args:
            parent: The parent buffer wrapper.
            index: Byte offset into the parent buffer.

        Returns:
            An attached ``CCPAttachedBuffer`` whose header points into the
            parent.

        Raises:
            BufferError: If the parent buffer was released.
            IndexError: If ``index`` is beyond the parent size.
        """
        ...

    @staticmethod
    def attached_header_addr(array: CCPAttachedBuffer) -> int:
        """The raw header pointer value of an attached wrapper.

        Args:
            array: The wrapper to inspect.

        Returns:
            The header pointer as an integer, 0 when NULL.
        """
        ...

    @staticmethod
    def attached_alloc_child(parent: CCPAttachedBuffer, size: int) -> CCPAttachedBuffer:
        """Allocate an attached child block owned by ``parent``.

        Args:
            parent: The parent buffer.
            size: Child buffer size in bytes.

        Returns:
            The new attached, owned child buffer.

        Raises:
            BufferError: If ``parent`` was released.
            MemoryError: If the allocation failed.
        """
        ...

    @staticmethod
    def attached_free_owned(array: CCPAttachedBuffer) -> None:
        """Free ``array`` together with its whole ownership tree.

        Args:
            array: The buffer to free recursively.
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
