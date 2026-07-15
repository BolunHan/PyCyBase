#ifndef REGEX_NT_COMPAT_H
#define REGEX_NT_COMPAT_H

#ifndef _WIN32
#error "regex_nt_compat.h is intended for Windows builds only"
#endif

#include <errno.h>
#include <stddef.h>

#if defined(__has_include)
#if __has_include(<Python.h>)
#include <Python.h>
#define REGEX_NT_COMPAT_HAS_PYTHON 1
#else
#define REGEX_NT_COMPAT_HAS_PYTHON 0
#endif
#else
#include <Python.h>
#define REGEX_NT_COMPAT_HAS_PYTHON 1
#endif

#ifndef REG_EXTENDED
#define REG_EXTENDED 1
#endif

#ifndef REG_NOMATCH
#define REG_NOMATCH 1
#endif

#ifndef REG_BADPAT
#define REG_BADPAT 2
#endif

typedef struct regex_t {
    PyObject* compiled;
} regex_t;

typedef struct regmatch_t {
    ptrdiff_t rm_so;
    ptrdiff_t rm_eo;
} regmatch_t;

#if REGEX_NT_COMPAT_HAS_PYTHON

static inline int regcomp(regex_t* regex, const char* pattern, int cflags) {
    (void) cflags;
    if (!regex || !pattern) {
        return REG_BADPAT;
    }

    regex->compiled = NULL;

    PyGILState_STATE gil_state = PyGILState_Ensure();
    PyObject*        re_module = PyImport_ImportModule("re");
    if (!re_module) {
        PyErr_Clear();
        PyGILState_Release(gil_state);
        return REG_BADPAT;
    }

    PyObject* compiled = PyObject_CallMethod(re_module, "compile", "s", pattern);
    Py_DECREF(re_module);
    if (!compiled) {
        PyErr_Clear();
        PyGILState_Release(gil_state);
        return REG_BADPAT;
    }

    regex->compiled = compiled;
    PyGILState_Release(gil_state);
    return 0;
}

static inline int regexec(const regex_t* regex, const char* string, size_t nmatch, regmatch_t pmatch[], int eflags) {
    (void) nmatch;
    (void) pmatch;
    (void) eflags;

    if (!regex || !regex->compiled || !string) {
        return REG_NOMATCH;
    }

    PyGILState_STATE gil_state = PyGILState_Ensure();
    PyObject*        match = PyObject_CallMethod(regex->compiled, "search", "s", string);
    if (!match) {
        PyErr_Clear();
        PyGILState_Release(gil_state);
        return REG_NOMATCH;
    }

    int result = (match == Py_None) ? REG_NOMATCH : 0;
    Py_DECREF(match);
    PyGILState_Release(gil_state);
    return result;
}

static inline void regfree(regex_t* regex) {
    if (!regex || !regex->compiled) {
        return;
    }

    PyGILState_STATE gil_state = PyGILState_Ensure();
    Py_DECREF(regex->compiled);
    regex->compiled = NULL;
    PyGILState_Release(gil_state);
}

#else

static inline int regcomp(regex_t* regex, const char* pattern, int cflags) {
    (void) regex;
    (void) pattern;
    (void) cflags;
    return REG_BADPAT;
}

static inline int regexec(const regex_t* regex, const char* string, size_t nmatch, regmatch_t pmatch[], int eflags) {
    (void) regex;
    (void) string;
    (void) nmatch;
    (void) pmatch;
    (void) eflags;
    return REG_NOMATCH;
}

static inline void regfree(regex_t* regex) {
    (void) regex;
}

#endif

#endif /* REGEX_NT_COMPAT_H */