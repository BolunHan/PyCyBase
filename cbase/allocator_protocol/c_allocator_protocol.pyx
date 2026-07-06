from libc.stdint cimport uintptr_t
from libc.stdlib cimport calloc

from .c_heap_allocator cimport C_ALLOCATOR as HEAP_ALLOCATOR
from .c_shm_allocator cimport C_ALLOCATOR as SHM_ALLOCATOR

cdef bint AP_CFG_LOCKED = False
cdef bint AP_CFG_SHARED = False
cdef bint AP_CFG_FREELIST = True


cdef class EnvConfigContext:
    def __cinit__(self, **kwargs):
        self.overrides = kwargs
        self.originals = {}

    cdef void c_activate(self):
        if 'locked' in self.overrides:
            global AP_CFG_LOCKED
            self.originals['locked'] = AP_CFG_LOCKED
            AP_CFG_LOCKED = self.overrides['locked']
            AP_DEFAULT_ALLOCATOR.with_lock = AP_CFG_LOCKED

        if 'shared' in self.overrides:
            global AP_CFG_SHARED
            self.originals['shared'] = AP_CFG_SHARED
            AP_CFG_SHARED = self.overrides['shared']
            AP_DEFAULT_ALLOCATOR.with_shm = AP_CFG_SHARED

        if 'freelist' in self.overrides:
            global AP_CFG_FREELIST
            self.originals['freelist'] = AP_CFG_FREELIST
            AP_CFG_FREELIST = self.overrides['freelist']
            AP_DEFAULT_ALLOCATOR.with_freelist = AP_CFG_FREELIST

    cdef void c_deactivate(self):
        if 'locked' in self.originals:
            global AP_CFG_LOCKED
            AP_CFG_LOCKED = self.originals.pop('locked')
            AP_DEFAULT_ALLOCATOR.with_lock = AP_CFG_LOCKED

        if 'shared' in self.originals:
            global AP_CFG_SHARED
            AP_CFG_SHARED = self.originals.pop('shared')
            AP_DEFAULT_ALLOCATOR.with_shm = AP_CFG_SHARED

        if 'freelist' in self.originals:
            global AP_CFG_FREELIST
            AP_CFG_FREELIST = self.originals.pop('freelist')

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
        merged_overrides = self.overrides | other.overrides
        return EnvConfigContext(**merged_overrides)

    def __invert__(self):
        return EnvConfigContext.__new__(
            EnvConfigContext,
            **{k: not v if isinstance(v, bool) else v for k, v in self.overrides.items()}
        )

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            self.c_activate()
            ret = func(*args, **kwargs)
            self.c_deactivate()
            return ret
        return wrapper


cdef EnvConfigContext AP_SHARED     = EnvConfigContext(shared=True)
cdef EnvConfigContext AP_LOCKED     = EnvConfigContext(locked=True)
cdef EnvConfigContext AP_FREELIST   = EnvConfigContext(freelist=True)


globals()['AP_SHARED'] = AP_SHARED
globals()['AP_LOCKED'] = AP_LOCKED
globals()['AP_FREELIST'] = AP_FREELIST


cdef class AllocatorProtocol:
    def __cinit__(self, size_t size):
        if not size:
            return
        if AP_CFG_SHARED:
            self.protocol = c_ap_allocator_protocol_new(size, SHM_ALLOCATOR, NULL, <int> AP_CFG_LOCKED)
        elif AP_CFG_FREELIST:
            self.protocol = c_ap_allocator_protocol_new(size, NULL, HEAP_ALLOCATOR, <int> AP_CFG_LOCKED)
        else:
            self.protocol = c_ap_allocator_protocol_new(size, NULL, NULL, 0)
        if self.protocol != NULL:
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

AP_DEFAULT_ALLOCATOR.with_lock          = AP_CFG_LOCKED
AP_DEFAULT_ALLOCATOR.with_shm           = AP_CFG_SHARED
AP_DEFAULT_ALLOCATOR.with_freelist      = AP_CFG_FREELIST
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
