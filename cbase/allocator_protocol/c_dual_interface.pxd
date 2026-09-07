from cpython.object cimport PyObject
from libc.stdint cimport uintptr_t

from .c_allocator_protocol cimport allocator_protocol, ap_callback_event


cdef extern from "cbase/allocator_protocol/c_dual_interface.h":
    ctypedef struct ccp_protocol_pyclass:
        PyObject ob_base
        allocator_protocol* ap_header
        uintptr_t ap_binding_id

    ctypedef struct ccp_bound_pyclass:
        ccp_protocol_pyclass ccp_protocol
        void* pyx_vtab
        void* header
        int owner

    void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) noexcept nogil

    int c_ccp_bind(object py_object) noexcept nogil
    int c_ccp_unbind(object py_object) noexcept nogil


cdef class CCPType:
    cdef allocator_protocol* ap_header
    cdef uintptr_t ap_binding_id


cdef class CCPDoubleArray(CCPType):
    cdef double* header
    cdef bint owner

    cdef readonly size_t size

    @staticmethod
    cdef CCPDoubleArray c_from_header(double* header, bint owner=?)
