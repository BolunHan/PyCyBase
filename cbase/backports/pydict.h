#ifndef PY_BACKPORTS_DICT_H
#define PY_BACKPORTS_DICT_H

/**
 * dict.h -- Python C API backports for dict operations.
 *
 * Provides shims so that Cython extensions can call a single function
 * regardless of the target Python version.  Each shim is exposed as a
 * ``static inline`` function when the target Python lacks the native API,
 * and as a thin ``#define`` alias when the native API is available.
 */

#include <Python.h>

/* ===================================================================
 * BP_PyDict_Pop  (native since Python 3.13 / PY_VERSION_HEX >= 0x030D0000)
 * ===================================================================
 *
 * int BP_PyDict_Pop(PyObject *op, PyObject *key, PyObject **result)
 *
 * Remove *key* from dictionary *op* and return the value (a new strong
 * reference) in **result*.
 *
 * Returns:  0 -- success (key found and removed)
 *           1 -- key not present
 *          -1 -- error (exception set, *result is NULL)
 */

#if PY_VERSION_HEX >= 0x030D0000
#define BP_PyDict_Pop PyDict_Pop
#else
static inline int BP_PyDict_Pop(PyObject* op, PyObject* key, PyObject** result) {
    PyObject* value = PyDict_GetItemWithError(op, key);
    if (!value) {
        /* NULL + exception -> error */
        if (PyErr_Occurred()) {
            *result = NULL;
            return -1;
        }
        /* NULL + no exception -> key not present */
        *result = NULL;
        return 1;
    }
    Py_INCREF(value);
    if (PyDict_DelItem(op, key) < 0) {
        Py_DECREF(value);
        *result = NULL;
        return -1;
    }
    *result = value;
    return 0;
}
#endif /* PY_VERSION_HEX >= 0x030D0000 */

#endif /* PY_BACKPORTS_DICT_H */
