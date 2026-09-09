#ifndef C_CCP_DUAL_INTERFACE_H
#define C_CCP_DUAL_INTERFACE_H

#include <Python.h>

#include <cbase/allocator_protocol/c_allocator_protocol.h>

// ========== Structs ==========

typedef void (*cpp_extra_dealloc_func)(PyObject* py_opbject);

typedef struct ccp_protocol {
    // === PyObject_HEAD ====
    PyObject_HEAD  // macro already ends with ';' since Python 3.11 - a trailing ';' makes an empty declaration, which MSVC's C frontend rejects (C2059)
    // === Pyx Virt Table ===
    void* __pyx_vtab;
    // === Allocator Protocol ====
    allocator_protocol*    ap_header;            // C-struct header binding point, the cdef class must ensure the exact binding position `cdef some_c_struct* header`
    uintptr_t              ap_binding_id;        // C-struct binding ID
    size_t                 ap_header_offset;     // C-header offset from PyObject*
    cpp_extra_dealloc_func cy_extra_dealloc_fn;  // Cy extra dealloc calls, prior to the nullifying of the header field
} ccp_protocol;

/**
 * @brief A simplest example of a CCP-protocol supported cdef class.
 *        Note that the actual layout might not be exact as this is.
 *        This is just a design pattern hint.
 */
typedef struct ccp_bound_pyclass {
    // === Base Protocol
    ccp_protocol ccp_ctx;
    // === Arbitrary fields (can contain multiple fields or not even exist) ===
    void* pyx_vtab;
    // === C Header ===
    void* header;
    int   owner;
} ccp_bound_pyclass;

// ========== Forward Declaration ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data);

static inline int  c_ccp_bind(PyObject* py_object, const void** c_header);
static inline int  c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header);
static inline int  c_ccp_unbind(PyObject* py_object);

// ========== Utilities Functions ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) {
    if (event == AP_CALLBACK_EVENT_FREE) {
        ccp_protocol* ccp = (ccp_protocol*) user_data;
        // Snapshot the offset before unbind clears the binding state.
        size_t header_offset = ccp->ap_header_offset;
        if (ccp->ap_header) {
            c_ccp_unbind((PyObject*) user_data);
        }

        if (header_offset) {
            cpp_extra_dealloc_func cy_extra_dealloc_fn = ccp->cy_extra_dealloc_fn;
            if (cy_extra_dealloc_fn) cy_extra_dealloc_fn((PyObject*) user_data);
            void** c_header = (void**) ((char*) user_data + header_offset);
            *c_header = NULL;
        }
    }
}

// ========== Public APIs ==========

static inline int c_ccp_bind(PyObject* py_object, const void** c_header) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    size_t              offset = (char*) c_header - (char*) py_object;
    const void*         header = *c_header;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = allocator_protocol;
    ccp->ap_header_offset = offset;
    c_ap_incref(header);
    return AP_OK;
}

static inline int c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    size_t              offset = (char*) c_header - (char*) py_object;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(parent_header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = allocator_protocol;
    ccp->ap_header_offset = offset;
    c_ap_incref(parent_header);
    return AP_OK;
}

static inline int c_ccp_unbind(PyObject* py_object) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    allocator_protocol* allocator_protocol = ccp->ap_header;
    if (!allocator_protocol) return AP_OK;  // Already unbound - idempotent.
    int ret_code = c_ap_unregister_callback(allocator_protocol, ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = NULL;
    ccp->ap_binding_id = 0;
    ccp->ap_header_offset = 0;
    c_ap_decref((const void*) allocator_protocol->buf);
    return AP_OK;
}

#endif  // C_CCP_DUAL_INTERFACE_H