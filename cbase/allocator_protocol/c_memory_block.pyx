cdef class MemoryBlock:
    """Common base for heap/SHM block handles.

    Tracks ownership of the underlying C buffer and holds a strong reference
    to the owning allocator (``__allocator__``), so an allocator can never be
    torn down while its blocks are still alive (e.g. interpreter-exit teardown
    order). Subclasses override ``_free_block`` to release the C buffer.
    """
    def __cinit__(self):
        self.owner = False
        self.__allocator__ = None

    cdef void _free_block(self):
        pass

    def __dealloc__(self):
        if not self.owner:
            return
        self._free_block()
        self.__allocator__ = None
