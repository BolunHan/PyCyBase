from libc.stdint cimport uintptr_t
from libc.stdlib cimport calloc

from .c_heap_allocator cimport C_ALLOCATOR as HEAP_ALLOCATOR
from .c_shm_allocator cimport C_ALLOCATOR as SHM_ALLOCATOR


cdef class EnvConfigContext:
    def __cinit__(self, **kwargs):
        self.overrides = kwargs
        self.originals = {}

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


cdef class AllocatorConfigContext(EnvConfigContext):
    cdef AllocatorConfigContext c_bind(self, allocator_protocol* schematic):
        self.allocator_schematic = schematic
        return self

    cdef void c_activate(self):
        if not self.allocator_schematic:
            raise RuntimeError(f'<{self.__class__.__name__}> not bound!')

        EnvConfigContext.c_activate(self)

        if 'locked' in self.overrides:
            self.originals['locked'] = self.allocator_schematic.with_lock
            self.allocator_schematic.with_lock = self.overrides['locked']

        if 'shared' in self.overrides:
            self.originals['shared'] = self.allocator_schematic.with_shm
            self.allocator_schematic.with_shm = self.overrides['shared']

        if 'freelist' in self.overrides:
            self.originals['freelist'] = self.allocator_schematic.with_freelist
            self.allocator_schematic.with_freelist = self.overrides['freelist']

    cdef void c_deactivate(self):
        if not self.allocator_schematic:
            raise RuntimeError(f'<{self.__class__.__name__}> not bound!')

        EnvConfigContext.c_deactivate(self)

        if 'locked' in self.originals:
            self.allocator_schematic.with_lock = self.originals.pop('locked')

        if 'shared' in self.originals:
            self.allocator_schematic.with_shm = self.originals.pop('shared')

        if 'freelist' in self.originals:
            self.allocator_schematic.with_freelist = self.originals.pop('freelist')

    def __or__(self, EnvConfigContext other):
        cdef dict merged_overrides = self.overrides | other.overrides
        cdef AllocatorConfigContext new_config = self.__class__(**merged_overrides)
        new_config.c_bind(self.allocator_schematic)
        return new_config

    def __invert__(self):
        cdef dict inverted_overrides = {k: not v if isinstance(v, bool) else v for k, v in self.overrides.items()}
        cdef AllocatorConfigContext new_config = self.__class__(**inverted_overrides)
        new_config.c_bind(self.allocator_schematic)
        return new_config


cdef class AllocatorProtocol:
    def __cinit__(self, size_t size):
        if not size:
            return

        if AP_DEFAULT_ALLOCATOR.with_shm:
            self.protocol = c_ap_allocator_protocol_new(size, SHM_ALLOCATOR, NULL, AP_DEFAULT_ALLOCATOR.with_lock)
        elif AP_DEFAULT_ALLOCATOR.with_freelist:
            self.protocol = c_ap_allocator_protocol_new(size, NULL, HEAP_ALLOCATOR, AP_DEFAULT_ALLOCATOR.with_lock)
        else:
            self.protocol = c_ap_allocator_protocol_new(size, NULL, NULL, 0)

        if self.protocol:
            c_ap_allocator_protocol_acquire_owner(self.protocol)

    def __dealloc__(self):
        if self.protocol:
            if c_ap_allocator_protocol_release_owner(self.protocol) == 0:
                c_ap_allocator_protocol_free(self.protocol)

    @staticmethod
    cdef AllocatorProtocol c_from_protocol(allocator_protocol* protocol):
        cdef AllocatorProtocol instance = AllocatorProtocol.__new__(AllocatorProtocol, 0)
        instance.protocol = protocol
        if protocol != NULL:
            c_ap_allocator_protocol_acquire_owner(protocol)
        return instance

    def __repr__(self):
        if not self.protocol:
            return f'<{self.__class__.__name__}>(Uninitialized)'
        return f'<{self.__class__.__name__} {<uintptr_t> self.protocol:#0x}>(with_shm={self.protocol.with_shm}, with_lock={self.protocol.with_lock}, size={self.protocol.size})'

    property with_lock:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            return self.protocol.with_lock

    property with_shm:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            return self.protocol.with_shm

    property with_freelist:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            return self.protocol.with_freelist

    property size:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            return self.protocol.size

    property buf:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            if self.protocol:
                return <char[:self.protocol.size]> self.protocol.buf
            return None

    property addr:
        def __get__(self):
            if not self.protocol:
                raise RuntimeError('allocator_protocol not initialized')
            return <uintptr_t> self.protocol


cdef allocator_protocol* AP_DEFAULT_ALLOCATOR   = <allocator_protocol*> calloc(1, sizeof(allocator_protocol))
cdef allocator_protocol* AP_SHM_ALLOCATOR       = <allocator_protocol*> calloc(1, sizeof(allocator_protocol))
cdef allocator_protocol* AP_HEAP_ALLOCATOR      = <allocator_protocol*> calloc(1, sizeof(allocator_protocol))

AP_DEFAULT_ALLOCATOR.with_lock          = AP_ALLOC_WITH_LOCK
AP_DEFAULT_ALLOCATOR.with_shm           = AP_ALLOC_WITH_SHM
AP_DEFAULT_ALLOCATOR.with_freelist      = AP_ALLOC_WITH_FREELIST
AP_DEFAULT_ALLOCATOR.shm_allocator_ctx  = SHM_ALLOCATOR
AP_DEFAULT_ALLOCATOR.shm_allocator      = SHM_ALLOCATOR.shm_allocator
AP_DEFAULT_ALLOCATOR.heap_allocator     = HEAP_ALLOCATOR

AP_SHM_ALLOCATOR.with_lock              = True
AP_SHM_ALLOCATOR.with_shm               = True
AP_SHM_ALLOCATOR.with_freelist          = True
AP_SHM_ALLOCATOR.shm_allocator_ctx      = SHM_ALLOCATOR
AP_SHM_ALLOCATOR.shm_allocator          = SHM_ALLOCATOR.shm_allocator
AP_SHM_ALLOCATOR.heap_allocator         = NULL

AP_HEAP_ALLOCATOR.with_lock             = True
AP_HEAP_ALLOCATOR.with_shm              = False
AP_HEAP_ALLOCATOR.with_freelist         = True
AP_HEAP_ALLOCATOR.shm_allocator_ctx     = NULL
AP_HEAP_ALLOCATOR.shm_allocator         = NULL
AP_HEAP_ALLOCATOR.heap_allocator        = HEAP_ALLOCATOR

cdef AllocatorConfigContext AP_SHARED   = AllocatorConfigContext(shared=True).c_bind(AP_DEFAULT_ALLOCATOR)
cdef AllocatorConfigContext AP_LOCKED   = AllocatorConfigContext(locked=True).c_bind(AP_DEFAULT_ALLOCATOR)
cdef AllocatorConfigContext AP_LOCKFREE = AllocatorConfigContext(locked=False).c_bind(AP_DEFAULT_ALLOCATOR)
cdef AllocatorConfigContext AP_FREELIST = AllocatorConfigContext(freelist=True).c_bind(AP_DEFAULT_ALLOCATOR)

globals()['AP_SHARED'] = AP_SHARED
globals()['AP_LOCKED'] = AP_LOCKED
globals()['AP_LOCKFREE'] = AP_LOCKFREE
globals()['AP_FREELIST'] = AP_FREELIST

