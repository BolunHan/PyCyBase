from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_Size
from libc.string cimport memcpy, memset, strlen

from .c_allocator_protocol cimport AP_DEFAULT_ALLOCATOR, ap_ret_code, c_ap_acquire_ownership, c_ap_alloc, c_ap_alloc_child, c_ap_free, c_ap_free_owned, c_ap_parent_of, c_ap_protocol_from_ptr, c_ap_realloc


cdef class CCPType:
    def __dealloc__(self):
        self.ccp_unbind()

    cdef void __ccp_dealloc__(self):
        pass

    cdef void ccp_bind(self, void* c_header):
        """signature as void* c_header as intended, only in this way the cython can skip the otherwise enforced type check."""
        cdef int ret_code = c_ccp_bind(<PyObject*> self, <const void**> c_header)
        if ret_code != ap_ret_code.AP_OK:
            raise BufferError(f'[CCP] Failed to bind <{self.__class__.__name__}> to allocator_protocol* {<uintptr_t> self.ap_header:#0x}')
        if <void*> self.__ccp_dealloc__ != <void*> CCPType.__ccp_dealloc__:
            self.cy_extra_dealloc_fn = <void*> self.__ccp_dealloc__

    cdef void ccp_bind_embedded(self, void* c_header, const void* parent_header):
        cdef int ret_code = c_ccp_bind_embedded(<PyObject*> self, <const void**> c_header, parent_header)
        if ret_code != ap_ret_code.AP_OK:
            raise BufferError(f'[CCP] Failed to bind embedded <{self.__class__.__name__}> to allocator_protocol* {<uintptr_t> self.ap_header:#0x}')
        if <void*> self.__ccp_dealloc__ != <void*> CCPType.__ccp_dealloc__:
            self.cy_extra_dealloc_fn = <void*> self.__ccp_dealloc__

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


cdef class CCPBoundBuffer(CCPType):
    def __init__(self, size_t size):
        self.header = <char*> c_ap_alloc(size, AP_DEFAULT_ALLOCATOR)
        if not self.header:
            raise MemoryError()

        self.size = size
        self.owner = True
        self.ccp_bind(&self.header)

    cdef void __ccp_dealloc__(self):
        self.size = 0

    def __dealloc__(self):
        if not self.owner:
            return

        if self.header:
            c_ap_free_owned(self.header)

    @staticmethod
    cdef CCPBoundBuffer c_from_header(char* header, bint owner=False):
        cdef CCPBoundBuffer instance = CCPBoundBuffer.__new__(CCPBoundBuffer)
        instance.header = header
        instance.owner = owner
        if header:
            instance.size = strlen(header)
        else:
            instance.size = 0
        return instance

    def self_dealloc(self):
        c_ap_free_owned(self.header)
        return self

    cdef CCPBoundBuffer c_alloc_child(self, size_t size):
        if not self.header:
            raise BufferError('parent buffer was released')

        cdef char* child = <char*> c_ap_alloc_child(size, NULL, self.header)
        if child == NULL:
            raise MemoryError(f'Failed to allocate child buffer of size {size}.')

        cdef CCPBoundBuffer instance = CCPBoundBuffer.__new__(CCPBoundBuffer)
        instance.header = child
        instance.owner = True
        instance.size = size
        instance.ccp_bind(&instance.header)
        return instance

    def alloc_child(self, size_t size):
        return self.c_alloc_child(size)

    cdef void c_free_owned(self):
        if not self.header:
            return
        c_ap_free_owned(self.header)

    def free_owned(self):
        self.c_free_owned()

    property values:
        def __get__(self):
            if not self.header:
                return None
            cdef bytes out = PyBytes_FromStringAndSize(self.header, self.size)
            return out

        def __set__(self, bytes values):
            if not self.header:
                raise BufferError('header was released')
            cdef size_t val_len = PyBytes_Size(values)
            if not val_len:
                raise RuntimeError()

            if val_len > self.size:
                memcpy(self.header, <const char*> values, self.size)
            else:
                memcpy(self.header, <const char*> values, val_len)
                memset(self.header + val_len, 0, self.size - val_len)


cdef class CCPDualInterfaceTestToolkit:
    """Test toolkit exposing the cdef-only CCPBoundBuffer operations to the
    Python unittest suite, driving all three binding scenarios: owned, view
    (ap-allocated block start, not owned), and embedded (interior pointer
    into a parent block)."""

    @staticmethod
    def c_from_header(uintptr_t header_addr, bint owner=False):
        return CCPBoundBuffer.c_from_header(<char*> header_addr, owner)

    @staticmethod
    def ccp_bind(CCPBoundBuffer array):
        array.ccp_bind(&array.header)

    @staticmethod
    def ccp_bind_embedded(CCPBoundBuffer array, uintptr_t parent_addr):
        array.ccp_bind_embedded(&array.header, <const void*> parent_addr)

    @staticmethod
    def ccp_unbind(CCPBoundBuffer array):
        array.ccp_unbind()

    @staticmethod
    def embedded_from(CCPBoundBuffer parent, size_t index):
        if not parent.header:
            raise BufferError('parent buffer was released')
        if index >= parent.size:
            raise IndexError(index)

        cdef CCPBoundBuffer instance = CCPBoundBuffer.c_from_header(parent.header + index, False)
        instance.ccp_bind_embedded(&instance.header, parent.header)
        return instance

    @staticmethod
    def header_addr(CCPBoundBuffer array):
        return <uintptr_t> array.header

    @staticmethod
    def alloc_child(CCPBoundBuffer parent, size_t size):
        return parent.c_alloc_child(size)

    @staticmethod
    def free_owned(CCPBoundBuffer array):
        array.c_free_owned()

    @staticmethod
    def realloc_owned(CCPBoundBuffer array, size_t new_size):
        if not array.header:
            raise BufferError('buffer was released')

        cdef allocator_protocol* allocator = c_ap_protocol_from_ptr(array.header)
        cdef char* old_header = array.header
        cdef char* new_header = <char*> c_ap_realloc(array.header, new_size, allocator)
        if new_header == NULL:
            array.header = NULL
            array.size = 0
            raise MemoryError(f'Failed to reallocate buffer to size {new_size}.')

        if new_header == old_header:
            # In-place shrink: the block (and its wrapper) is unchanged.
            array.size = new_size
            return array

        # Moved: the old block's FREE pass husked `array` when it was
        # bound; null it unconditionally so unbound wrappers never dangle.
        array.header = NULL
        array.size = 0

        cdef CCPBoundBuffer instance = CCPBoundBuffer.__new__(CCPBoundBuffer)
        instance.header = new_header
        instance.owner = True
        instance.size = new_size
        instance.ccp_bind(&instance.header)
        return instance

    @staticmethod
    def hierarchy_addr(CCPBoundBuffer array):
        if not array.header:
            raise BufferError('buffer was released')

        cdef allocator_protocol* protocol = c_ap_protocol_from_ptr(array.header)
        # c_ap_parent_of returns the parent block start — derive its protocol
        # so all four slots report protocol addresses.
        return (<uintptr_t> c_ap_protocol_from_ptr(c_ap_parent_of(array.header)), <uintptr_t> protocol.first_child,
                <uintptr_t> protocol.next_sibling, <uintptr_t> protocol.prev_sibling)

    @staticmethod
    def acquire_ownership(CCPBoundBuffer array, uintptr_t new_parent_addr=0):
        if not array.header:
            raise BufferError('buffer was released')
        c_ap_acquire_ownership(array.header, <const void*> new_parent_addr)

    @staticmethod
    def protocol_addr(CCPBoundBuffer array):
        if not array.header:
            raise BufferError('buffer was released')
        return <uintptr_t> c_ap_protocol_from_ptr(array.header)

    @staticmethod
    def raw_free(CCPBoundBuffer array):
        c_ap_free(array.header)
