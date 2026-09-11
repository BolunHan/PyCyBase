from cpython.object cimport PyObject
from libc.stdint cimport uintptr_t

from .c_allocator_protocol cimport allocator_protocol, ap_callback_event


cdef extern from "cbase/allocator_protocol/c_dual_interface.h":
    ctypedef void (*cpp_extra_dealloc_func)(PyObject* py_opbject) noexcept

    ctypedef struct ccp_ctx:
        allocator_protocol* ap_header
        uintptr_t ap_binding_id
        size_t ccp_header_offset
        size_t ccp_ctx_offset
        cpp_extra_dealloc_func cy_extra_dealloc_fn

    ctypedef struct ccp_protocol:
        PyObject ob_base
        void* pyx_vtab
        ccp_ctx ctx

    ctypedef struct ccp_bound_pyclass:
        ccp_protocol protocol
        void* pyx_vtab
        void* header
        int owner

    void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) noexcept nogil
    void c_ccp_context_callback_adaptor(ap_callback_event event, void* buf, void* user_data) noexcept nogil

    int c_ccp_bind(PyObject* py_object, const void** c_header) noexcept nogil
    int c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header) noexcept nogil
    int c_ccp_unbind(PyObject* py_object) noexcept nogil

    int c_ccp_attach(PyObject* py_object, const void** c_header, ccp_ctx* ccp) noexcept nogil
    int c_ccp_attach_embedded(PyObject* py_object, const void** c_header, ccp_ctx* ccp, const void* parent_header) noexcept nogil
    int c_ccp_detach(PyObject* py_object, ccp_ctx* ccp) noexcept nogil


cdef class CCPType:
    cdef allocator_protocol* ap_header
    cdef uintptr_t ap_binding_id
    cdef size_t ccp_header_offset
    cdef size_t ccp_ctx_offset
    cdef void* cy_extra_dealloc_fn

    cdef void __ccp_dealloc__(self)

    cdef void ccp_bind(self, void* c_header)

    cdef void ccp_bind_embedded(self, void* c_header, const void* parent_header)

    cdef void ccp_unbind(self)

    @staticmethod
    cdef inline void ccp_attach(PyObject* py_object, const void** c_header, ccp_ctx* ccp, void* dealloc_fn) except *

    @staticmethod
    cdef inline void ccp_attach_embedded(PyObject* py_object, const void** c_header, ccp_ctx* ccp, const void* parent_header, void* dealloc_fn) except *

    @staticmethod
    cdef inline void ccp_detach(PyObject* py_object, ccp_ctx* ccp) except *


cdef class BoundBuffer:
    cdef char* header
    cdef bint owner

    cdef readonly size_t size

    @staticmethod
    cdef BoundBuffer c_from_header(char* header, bint owner=?)

    cdef BoundBuffer c_alloc_child(self, size_t size)

    cdef void c_free_owned(self)


cdef class CCPAttachedBuffer(BoundBuffer):
    cdef ccp_ctx ccp_ctx

    cdef void __ccp_dealloc__(self)

    cdef void ccp_attach(self)

    cdef void ccp_attach_embedded(self, const void* parent_header)

    cdef void ccp_detach(self)

    @staticmethod
    cdef CCPAttachedBuffer c_from_header(char* header, bint owner=?)

    @staticmethod
    cdef CCPAttachedBuffer c_from_header_embedded(char* header, const void* parent_header)

    cdef CCPAttachedBuffer c_alloc_child(self, size_t size)



cdef class CCPBoundBuffer(CCPType):
    cdef char* header
    cdef bint owner

    cdef readonly size_t size

    @staticmethod
    cdef CCPBoundBuffer c_from_header(char* header, bint owner=?)

    @staticmethod
    cdef CCPBoundBuffer c_from_header_embedded(char* header, const void* parent_header)

    cdef CCPBoundBuffer c_alloc_child(self, size_t size)

    cdef void c_free_owned(self)


cdef class CCPDualInterfaceTestToolkit:
    pass
