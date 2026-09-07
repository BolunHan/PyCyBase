from .c_allocator_protocol cimport c_ap_alloc, c_ap_free, AP_DEFAULT_ALLOCATOR


cdef class CCPType:
    def __dealloc__(self):
        c_ccp_unbind(self)



cdef class CCPDoubleArray(CCPType):
    def __init__(self, size_t size):
        self.header = <double*> c_ap_alloc(size * sizeof(double), AP_DEFAULT_ALLOCATOR)
        if not self.header:
            raise MemoryError()

        self.size = size
        self.owner = True
        c_ccp_bind(self)

    def __dealloc__(self):
        if not self.owner:
            return

        if self.header:
            c_ap_free(self.header)

    @staticmethod
    cdef CCPDoubleArray c_from_header(double* header, bint owner=False):
        cdef CCPDoubleArray instance = CCPDoubleArray.__new__(CCPDoubleArray)
        instance.header = header
        instance.owner = owner
        c_ccp_bind(instance)
        return instance

    def self_dealloc(self):
        c_ap_free(self.header)
        return self

    property values:
        def __get__(self):
            cdef size_t i
            cdef list out = []
            for i in range(self.size):
                out.append(self.header[i])
            return out

        def __set__(self, list values):
            cdef size_t i
            assert (<size_t> len(values)) == self.size
            for i in range(self.size):
                self.header[i] = <double> values[i]
