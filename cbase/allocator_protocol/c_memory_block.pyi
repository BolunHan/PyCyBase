class MemoryBlock:
    """Common base for heap/SHM block handles.

    Tracks ownership of the underlying C buffer and holds a strong reference
    to the owning allocator so it can never be torn down while its blocks are
    still alive (e.g. interpreter-exit teardown order).

    Attributes:
        owner: True when this handle owns the underlying C buffer and releases
            it on deallocation.
    """

    owner: bool

    def __init__(self) -> None: ...
