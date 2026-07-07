
cdef class EnvConfigContext:
    def __cinit__(self):
        self.overrides = {}
        self.originals = {}

    def __init__(self, dict overrides=None, **kwargs):
        if overrides:
            self.overrides.update(overrides)

        if kwargs:
            self.overrides.update(kwargs)

    cdef void c_activate(self):
        pass

    cdef void c_deactivate(self):
        pass

    def __repr__(self):
        return f'{self.__class__.__name__}({self.overrides!r})'

    def __enter__(self):
        self.c_activate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.c_deactivate()

    def __or__(self, EnvConfigContext other):
        if not isinstance(other, EnvConfigContext):
            return NotImplemented
        cdef dict merged_overrides = self.overrides | other.overrides
        return self.__class__(**merged_overrides)

    def __invert__(self):
        cdef dict inverted_overrides = {k: not v if isinstance(v, bool) else v for k, v in self.overrides.items()}
        return self.__class__(**inverted_overrides)

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            self.c_activate()
            ret = func(*args, **kwargs)
            self.c_deactivate()
            return ret
        return wrapper
