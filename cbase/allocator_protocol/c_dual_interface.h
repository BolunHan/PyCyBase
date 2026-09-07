#ifndef C_CCP_DUAL_INTERFACE_H
#define C_CCP_DUAL_INTERFACE_H

#include <Python.h>

#include <cbase/allocator_protocol/c_allocator_protocol.h>

// ========== Structs ==========

typedef struct ccp_protocol_pyclass {
    // === PyObject_HEAD ====
    PyObject            ob_base;
    allocator_protocol* ap_header;      // C-struct header binding point, the cdef class must ensure the exact binding position `cdef some_c_struct* header`
    uintptr_t           ap_binding_id;  // C-struct binding ID
} ccp_protocol_pyclass;

typedef struct ccp_bound_pyclass {
    ccp_protocol_pyclass ccp_protocol;
    void*                pyx_vtab;
    void*                header;
    int                  owner;  // Optional owner field
} ccp_bound_pyclass;

// ========== Forward Declaration ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data);

static inline int  c_ccp_bind(PyObject* py_object);
static inline int  c_ccp_unbind(PyObject* py_object);
static inline int c_ccp_bind_embedded(PyObject* py_object, const void* parent_header);

// ========== Utilities Functions ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) {
    if (event == AP_CALLBACK_EVENT_DEALLOC) {
        ccp_bound_pyclass* bound_class = (ccp_bound_pyclass*) user_data;
        if (bound_class->ccp_protocol.ap_header) c_ccp_unbind((PyObject*) bound_class);
        bound_class->header = NULL;
    }
}

// ========== Public APIs ==========

static inline int c_ccp_bind(PyObject* py_object) {
    ccp_bound_pyclass*  bound_pyclass = (ccp_bound_pyclass*) py_object;
    void*               header = bound_pyclass->header;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &bound_pyclass->ccp_protocol.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    bound_pyclass->ccp_protocol.ap_header = allocator_protocol;
    c_ap_incref(header);
    return AP_OK;
}

static inline int c_ccp_bind_embedded(PyObject* py_object, const void* parent_header) {
    ccp_bound_pyclass*  bound_pyclass = (ccp_bound_pyclass*) py_object;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(parent_header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &bound_pyclass->ccp_protocol.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    bound_pyclass->ccp_protocol.ap_header = allocator_protocol;
    c_ap_incref(parent_header);
    return AP_OK;
}

static inline int c_ccp_unbind(PyObject* py_object) {
    ccp_bound_pyclass*  bound_pyclass = (ccp_bound_pyclass*) py_object;
    allocator_protocol* allocator_protocol = bound_pyclass->ccp_protocol.ap_header;
    int                 ret_code = c_ap_unregister_callback(allocator_protocol, bound_pyclass->ccp_protocol.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    bound_pyclass->ccp_protocol.ap_header = NULL;
    bound_pyclass->ccp_protocol.ap_binding_id = 0;
    c_ap_decref(bound_pyclass->header);
    return AP_OK;
}

#endif  // C_CCP_DUAL_INTERFACE_H