#ifndef C_CCP_DUAL_INTERFACE_H
#define C_CCP_DUAL_INTERFACE_H

#include <Python.h>

#include <cbase/allocator_protocol/c_allocator_protocol.h>

// ========== Structs ==========

// clang-format off

typedef void (*cpp_extra_dealloc_func)(PyObject* py_opbject);

/**
 * @brief CCP binding state shared by the bound and attached binding variants.
 */
typedef struct ccp_ctx {
    allocator_protocol*    ap_header;            // C-struct header binding point, the cdef class must ensure the exact binding position `cdef some_c_struct* header`
    uintptr_t              ap_binding_id;        // C-struct binding ID
    size_t                 ccp_header_offset;    // C-header offset from PyObject*
    size_t                 ccp_ctx_offset;       // CCP context offset from PyObject*, when used in attached mode
    cpp_extra_dealloc_func cy_extra_dealloc_fn;  // Cy extra dealloc calls, prior to the nullifying of the header field
} ccp_ctx;

/**
 * @brief C translation of the `CCPType` cdef class layout (bound variant).
 */
typedef struct ccp_protocol {
    // === PyObject_HEAD ====
    PyObject_HEAD  // macro already ends with ';' since Python 3.11 - a trailing ';' makes an empty declaration, which MSVC's C frontend rejects (C2059)
    // === Pyx Virt Table ===
    void* __pyx_vtab;
    // === Binding State ===
    ccp_ctx ctx;
} ccp_protocol;

/**
 * @brief A simplest example of a CCP-protocol supported cdef class.
 *        Note that the actual layout might not be exact as this is.
 *        This is just a design pattern hint.
 */
typedef struct ccp_bound_pyclass {
    // === Base Protocol
    ccp_protocol protocol;
    // === Arbitrary fields (can contain multiple fields or not even exist) ===
    void* pyx_vtab;
    // === C Header ===
    void* header;
    int   owner;
} ccp_bound_pyclass;

// clang-format on

// ========== Forward Declaration ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data);
static inline void c_ccp_context_callback_adaptor(ap_callback_event event, void* buf, void* user_data);

static inline int  c_ccp_bind(PyObject* py_object, const void** c_header);
static inline int  c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header);
static inline int  c_ccp_unbind(PyObject* py_object);

static inline int  c_ccp_attach(PyObject* py_object, const void** c_header, ccp_ctx* ccp);
static inline int  c_ccp_attach_embedded(PyObject* py_object, const void** c_header, ccp_ctx* ccp, const void* parent_header);
static inline int  c_ccp_detach(PyObject* py_object, ccp_ctx* ccp);

// ========== Utilities Functions ==========

static inline void c_ccp_bound_callback_adaptor(ap_callback_event event, void* buf, void* user_data) {
    if (event == AP_CALLBACK_EVENT_FREE) {
        ccp_protocol* ccp = (ccp_protocol*) user_data;
        // Snapshot the offset before unbind clears the binding state.
        size_t header_offset = ccp->ctx.ccp_header_offset;
        if (ccp->ctx.ap_header) {
            c_ccp_unbind((PyObject*) user_data);
        }

        if (header_offset) {
            cpp_extra_dealloc_func cy_extra_dealloc_fn = ccp->ctx.cy_extra_dealloc_fn;
            if (cy_extra_dealloc_fn) cy_extra_dealloc_fn((PyObject*) user_data);
            void** c_header = (void**) ((char*) user_data + header_offset);
            *c_header = NULL;
        }
    }
}

static inline void c_ccp_context_callback_adaptor(ap_callback_event event, void* buf, void* user_data) {
    if (event == AP_CALLBACK_EVENT_FREE) {
        ccp_ctx*  ccp = (ccp_ctx*) user_data;
        size_t    ccp_offset = ccp->ccp_ctx_offset;
        size_t    header_offset = ccp->ccp_header_offset;
        PyObject* py_object = (PyObject*) ((char*) user_data - ccp_offset);
        if (ccp->ap_header) {
            c_ccp_detach(py_object, ccp);
        }

        if (header_offset) {
            cpp_extra_dealloc_func cy_extra_dealloc_fn = ccp->cy_extra_dealloc_fn;
            if (cy_extra_dealloc_fn) cy_extra_dealloc_fn(py_object);
            void** c_header = (void**) ((char*) py_object + header_offset);
            *c_header = NULL;
        }
    }
}

// ========== Public APIs (Inheritance Protocol) ==========

static inline int c_ccp_bind(PyObject* py_object, const void** c_header) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    size_t              offset = (char*) c_header - (char*) py_object;
    const void*         header = *c_header;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &ccp->ctx.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ctx.ap_header = allocator_protocol;
    ccp->ctx.ccp_header_offset = offset;
    c_ap_incref(header);
    return AP_OK;
}

static inline int c_ccp_bind_embedded(PyObject* py_object, const void** c_header, const void* parent_header) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    size_t              offset = (char*) c_header - (char*) py_object;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(parent_header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_bound_callback_adaptor, py_object, &ccp->ctx.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ctx.ap_header = allocator_protocol;
    ccp->ctx.ccp_header_offset = offset;
    c_ap_incref(parent_header);
    return AP_OK;
}

static inline int c_ccp_unbind(PyObject* py_object) {
    ccp_protocol*       ccp = (ccp_protocol*) py_object;
    allocator_protocol* allocator_protocol = ccp->ctx.ap_header;
    if (!allocator_protocol) return AP_OK;  // Already unbound - idempotent.
    int ret_code = c_ap_unregister_callback(allocator_protocol, ccp->ctx.ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ctx.ap_header = NULL;
    ccp->ctx.ap_binding_id = 0;
    ccp->ctx.ccp_header_offset = 0;
    c_ap_decref((const void*) allocator_protocol->buf);
    return AP_OK;
}

// ========== Public APIs (Attachment Protocol) ==========

/**
 * @brief Attach a wrapper's embedded ccp_ctx to a block-start buffer.
 *
 * The attached variant locates the binding state through the embedded
 * `ccp_ctx` value field (`ccp`) instead of casting the object to
 * `ccp_protocol`, so the wrapper is not required to inherit `CCPType` at
 * a fixed layout position.
 *
 * @param py_object The wrapper object.
 * @param c_header  Address of the wrapper's header field.
 * @param ccp       Address of the wrapper's embedded ccp_ctx value field.
 * @return AP_OK or a negative error code.
 */
static inline int c_ccp_attach(PyObject* py_object, const void** c_header, ccp_ctx* ccp) {
    if (!py_object || !c_header || !ccp) return AP_ERR_INVALID_ARG;
    size_t              ccp_offset = (char*) ccp - (char*) py_object;
    size_t              c_offset = (char*) c_header - (char*) py_object;
    const void*         header = *c_header;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_context_callback_adaptor, ccp, &ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = allocator_protocol;
    ccp->ccp_header_offset = c_offset;
    ccp->ccp_ctx_offset = ccp_offset;
    c_ap_incref(header);
    return AP_OK;
}

/**
 * @brief Attach a wrapper whose header is an interior pointer of a parent block.
 *
 * @param py_object     The wrapper object.
 * @param c_header      Address of the wrapper's header field.
 * @param ccp           Address of the wrapper's embedded ccp_ctx value field.
 * @param parent_header The parent block start.
 * @return AP_OK or a negative error code.
 */
static inline int c_ccp_attach_embedded(PyObject* py_object, const void** c_header, ccp_ctx* ccp, const void* parent_header) {
    if (!py_object || !c_header || !ccp) return AP_ERR_INVALID_ARG;
    size_t              ccp_offset = (char*) ccp - (char*) py_object;
    size_t              c_offset = (char*) c_header - (char*) py_object;
    allocator_protocol* allocator_protocol = c_ap_protocol_from_ptr(parent_header);
    int                 ret_code = c_ap_register_callback(allocator_protocol, c_ccp_context_callback_adaptor, ccp, &ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = allocator_protocol;
    ccp->ccp_header_offset = c_offset;
    ccp->ccp_ctx_offset = ccp_offset;
    c_ap_incref(parent_header);
    return AP_OK;
}

/**
 * @brief Release a wrapper's attachment; idempotent when already detached.
 *
 * @param py_object The wrapper object.
 * @param ccp       The wrapper's embedded ccp_ctx.
 * @return AP_OK or a negative error code.
 */
static inline int c_ccp_detach(PyObject* py_object, ccp_ctx* ccp) {
    allocator_protocol* allocator_protocol = ccp->ap_header;
    if (!allocator_protocol) return AP_OK;  // Already unbound - idempotent.
    int ret_code = c_ap_unregister_callback(allocator_protocol, ccp->ap_binding_id);
    if (ret_code != AP_OK) return ret_code;
    ccp->ap_header = NULL;
    ccp->ap_binding_id = 0;
    ccp->ccp_header_offset = 0;
    ccp->ccp_ctx_offset = 0;
    c_ap_decref((const void*) allocator_protocol->buf);
    return AP_OK;
}

#endif  // C_CCP_DUAL_INTERFACE_H
