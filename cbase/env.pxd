
cdef class EnvConfigContext:
    cdef dict overrides
    cdef dict originals

    cdef void c_activate(self)

    cdef void c_deactivate(self)
