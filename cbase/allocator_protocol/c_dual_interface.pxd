from cpython.object cimport PyObject
from libc.stdint cimport uintptr_t

from .c_allocator_protocol cimport allocator_protocol, ap_callback_event


cdef extern from "cbase/allocator_protocol/c_dual_interface.h":
    ctypedef void (*cpp_extra_dealloc_func)(PyObject* py_opbject) noexcept

    ctypedef struct ccp_protocol:
        PyObject ob_base
        void* pyx_vtab
        allocator_protocol* ap_header
        uintptr_t ap_binding_id
        size_t ap_header_offset
        cpp_extra_dealloc_func cy_extra_dealloc_fn

    ctypedef struct ccp_bound_pyclass:
        ccp_protocol ccp_ctx
        void* pyx_vtab
        void* header
        int owner

    void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) noexcept nogil

    int c_ccp_bind(PyObject* py_object, const void** c_header) noexcept nogil
    int c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header) noexcept nogil
    int c_ccp_unbind(PyObject* py_object) noexcept nogil


cdef class CCPType:
    cdef allocator_protocol* ap_header
    cdef uintptr_t ap_binding_id
    cdef size_t ap_header_offset
    cdef void* cy_extra_dealloc_fn

    cdef void __ccp_dealloc__(self)

    cdef void ccp_bind(self, void* c_header)

    cdef void ccp_bind_embedded(self, void* c_header, const void* parent_header)

    cdef void ccp_unbind(self)


cdef class CCPBoundBuffer(CCPType):
    cdef char* header
    cdef bint owner

    cdef readonly size_t size

    @staticmethod
    cdef CCPBoundBuffer c_from_header(char* header, bint owner=?)

    cdef CCPBoundBuffer c_alloc_child(self, size_t size)

    cdef void c_free_owned(self)


cdef class CCPDualInterfaceTestToolkit:
    pass
