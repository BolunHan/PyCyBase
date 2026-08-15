cdef class MemoryBlock:
    cdef readonly bint owner
    cdef object __allocator__

    cdef void _free_block(self)
