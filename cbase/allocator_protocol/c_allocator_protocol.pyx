from libc.stdint cimport uintptr_t
from libc.stdlib cimport calloc

from .c_heap_allocator cimport C_ALLOCATOR as HEAP_ALLOCATOR
from .c_shm_allocator cimport C_ALLOCATOR as SHM_ALLOCATOR


cdef class AllocatorConfigContext(EnvConfigContext):
    def __init__(self, dict overrides=None, **kwargs):
        super().__init__(overrides, **kwargs)
        self.c_bind()

    cdef void c_bind(self, allocator_protocol* schematic=NULL):
        self.allocator_schematic = schematic if schematic else AP_DEFAULT_ALLOCATOR

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

        if 'autopage_capacity' in self.overrides:
            if self.allocator_schematic.heap_allocator:
                self.originals['heap.autopage_capacity'] = self.allocator_schematic.heap_allocator.autopage_capacity
                self.allocator_schematic.heap_allocator.autopage_capacity = self.overrides['autopage_capacity']
            if self.allocator_schematic.shm_allocator_ctx and self.allocator_schematic.shm_allocator_ctx.shm_allocator:
                self.originals['shm.autopage_capacity'] = self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity
                self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity = self.overrides['autopage_capacity']

        if 'autopage_capacity_max' in self.overrides:
            if self.allocator_schematic.heap_allocator:
                self.originals['heap.autopage_capacity_max'] = self.allocator_schematic.heap_allocator.autopage_capacity_max
                self.allocator_schematic.heap_allocator.autopage_capacity_max = self.overrides['autopage_capacity_max']
            if self.allocator_schematic.shm_allocator_ctx and self.allocator_schematic.shm_allocator_ctx.shm_allocator:
                self.originals['shm.autopage_capacity_max'] = self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity_max
                self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity_max = self.overrides['autopage_capacity_max']

        if 'autopage_alignment' in self.overrides:
            if self.allocator_schematic.heap_allocator:
                self.originals['heap.autopage_alignment'] = self.allocator_schematic.heap_allocator.autopage_alignment
                self.allocator_schematic.heap_allocator.autopage_alignment = self.overrides['autopage_alignment']
            if self.allocator_schematic.shm_allocator_ctx and self.allocator_schematic.shm_allocator_ctx.shm_allocator:
                self.originals['shm.autopage_alignment'] = self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_alignment
                self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_alignment = self.overrides['autopage_alignment']

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

        if 'heap.autopage_capacity' in self.originals:
            self.allocator_schematic.heap_allocator.autopage_capacity = self.originals.pop('heap.autopage_capacity')

        if 'shm.autopage_capacity' in self.originals:
            self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity = self.originals.pop('shm.autopage_capacity')

        if 'heap.autopage_capacity_max' in self.originals:
            self.allocator_schematic.heap_allocator.autopage_capacity_max = self.originals.pop('heap.autopage_capacity_max')

        if 'shm.autopage_capacity_max' in self.originals:
            self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_capacity_max = self.originals.pop('shm.autopage_capacity_max')

        if 'heap.autopage_alignment' in self.originals:
            self.allocator_schematic.heap_allocator.autopage_alignment = self.originals.pop('heap.autopage_alignment')

        if 'shm.autopage_alignment' in self.originals:
            self.allocator_schematic.shm_allocator_ctx.shm_allocator.autopage_alignment = self.originals.pop('shm.autopage_alignment')

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

cdef AllocatorConfigContext AP_SHARED   = AllocatorConfigContext(shared=True)
cdef AllocatorConfigContext AP_LOCKED   = AllocatorConfigContext(locked=True)
cdef AllocatorConfigContext AP_LOCKFREE = AllocatorConfigContext(locked=False)
cdef AllocatorConfigContext AP_FREELIST = AllocatorConfigContext(freelist=True)

globals()['AP_SHARED'] = AP_SHARED
globals()['AP_LOCKED'] = AP_LOCKED
globals()['AP_LOCKFREE'] = AP_LOCKFREE
globals()['AP_FREELIST'] = AP_FREELIST
