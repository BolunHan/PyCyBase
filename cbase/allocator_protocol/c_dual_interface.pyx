from .c_allocator_protocol cimport c_ap_alloc, c_ap_free, AP_DEFAULT_ALLOCATOR, ap_ret_code


cdef class CCPType:
    def __dealloc__(self):
        self.ccp_unbind()

    cdef void ccp_bind(self, void* c_header):
        """signature as void* c_header as intended, only in this way the cython can skip the otherwise enforced type check."""
        cdef int ret_code = c_ccp_bind(<PyObject*> self, <const void**> c_header)
        if ret_code == ap_ret_code.AP_OK:
            return
        raise BufferError(f'[CCP] Failed to bind <{self.__class__.__name__}> to allocator_protocol* {<uintptr_t> self.ap_header:#0x}')

    cdef void ccp_bind_embedded(self, void* c_header, const void* parent_header):
        cdef int ret_code = c_ccp_bind_embedded(<PyObject*> self, <const void**> c_header, parent_header)
        if ret_code == ap_ret_code.AP_OK:
            return
        raise BufferError(f'[CCP] Failed to bind embedded <{self.__class__.__name__}> to allocator_protocol* {<uintptr_t> self.ap_header:#0x}')

    cdef void ccp_unbind(self):
        cdef int ret_code = c_ccp_unbind(<PyObject*> self)
        if ret_code == ap_ret_code.AP_OK:
            return
        raise BufferError(f'[CCP] Failed to unbind embedded from allocator_protocol* {<uintptr_t> self.ap_header:#0x}')

    property address:
        def __get__(self):
            if not self.ap_header:
                return 'NULL'
            return f'{<uintptr_t> self.ap_header.buf:#0x}'


cdef class CCPDoubleArray(CCPType):
    def __init__(self, size_t size):
        self.header = <double*> c_ap_alloc(size * sizeof(double), AP_DEFAULT_ALLOCATOR)
        if not self.header:
            raise MemoryError()

        self.size = size
        self.owner = True
        self.ccp_bind(&self.header)

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
        instance.ccp_bind(&instance.header)
        return instance

    def self_dealloc(self):
        c_ap_free(self.header)
        return self

    property values:
        def __get__(self):
            if not self.header:
                return None
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
