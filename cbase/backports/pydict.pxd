from cpython.object cimport PyObject


cdef extern from "cbase/backports/pydict.h":
    int BP_PyDict_Pop(PyObject* p, PyObject* key, PyObject** result)
