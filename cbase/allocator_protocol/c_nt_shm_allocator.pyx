"""NT-native shared memory allocator (Windows-only).

Provides NtSharedMemoryAllocator — a crude, test-focused wrapper around
c_nt_shm_allocator.h.  Uses Windows kernel objects (CreateFileMappingW,
MapViewOfFile, named mutexes) instead of POSIX SHM.
"""
from cpython.unicode cimport PyUnicode_FromString, PyUnicode_AsUTF8
from libc.errno cimport errno


cdef class NtSharedMemoryAllocator:
    """Windows-native shared memory allocator.

    Mirrors the POSIX SharedMemoryAllocator API but uses NT kernel objects:
    - CreateFileMappingW for named shared memory
    - MapViewOfFile / UnmapViewOfFile for mapping
    - CreateMutexW for inter-process synchronization
    """

    def __init__(
        self,
        size_t region_size=AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE,
        str shm_prefix=None
    ):
        if not region_size:
            return
        cdef const char* prefix = PyUnicode_AsUTF8(shm_prefix) if shm_prefix else NULL
        self.ctx = c_nt_shm_allocator_new(region_size, prefix)
        if not self.ctx:
            raise OSError(errno, "Initialize NT SHM allocator failed")
        self.owner = True

    def __dealloc__(self):
        if not self.owner:
            return
        if self.ctx:
            c_nt_shm_allocator_free(self.ctx)

    cdef inline void* c_calloc(self, size_t size, pthread_mutex_t* lock=NULL):
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        return c_nt_shm_calloc(self.ctx, size, lock)

    cdef inline void* c_request(self, size_t size, int scan_all_pages=1, pthread_mutex_t* lock=NULL):
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        return c_nt_shm_request(self.ctx, size, scan_all_pages, lock)

    cdef inline void c_free(self, void* ptr, pthread_mutex_t* lock=NULL):
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        c_nt_shm_free(ptr, lock)

    def __repr__(self):
        if self.ctx and self.ctx.shm_allocator:
            return (
                f"<{self.__class__.__name__}"
                f"(name={self.name}, pid={self.pid})>"
            )
        return f"<{self.__class__.__name__}(uninitialized)>"

    # -- Public Python API ---------------------------------------------------

    cpdef object calloc(self, size_t size, bint with_lock=True):
        """Allocate zeroed memory.  Returns a read-write memoryview of ``size`` bytes."""
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        cdef pthread_mutex_t* lock = &self.ctx.shm_allocator.lock if with_lock else NULL
        cdef void* p = c_nt_shm_calloc(self.ctx, size, lock)
        if not p:
            raise OSError(
                errno,
                f"<{self.__class__.__name__}> failed to calloc {size} bytes",
            )
        cdef unsigned char[:] view = <unsigned char[:size]>p
        return view

    cpdef object request(self, size_t size, bint scan_all_pages=True, bint with_lock=True):
        """Allocate memory (reuses freed blocks).  Returns a read-write memoryview."""
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        cdef pthread_mutex_t* lock = &self.ctx.shm_allocator.lock if with_lock else NULL
        cdef void* p = c_nt_shm_request(self.ctx, size, scan_all_pages, lock)
        if not p:
            raise OSError(
                errno,
                f"<{self.__class__.__name__}> failed to request {size} bytes",
            )
        cdef unsigned char[:] view = <unsigned char[:size]>p
        return view

    cpdef void free(self, object buffer, bint with_lock=True):
        """Return a previously allocated buffer to the free list."""
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        if buffer is None:
            return
        cdef const unsigned char[::1] view = buffer
        cdef void* ptr = <void*>&view[0]
        cdef pthread_mutex_t* lock = &self.ctx.shm_allocator.lock if with_lock else NULL
        if ptr:
            c_nt_shm_free(ptr, lock)

    cpdef void reclaim(self, bint with_lock=True):
        """Run best-effort reclaim of freed blocks across all pages."""
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        cdef pthread_mutex_t* lock = &self.ctx.shm_allocator.lock if with_lock else NULL
        c_nt_shm_reclaim(self.ctx, lock)

    cpdef object extend(self, size_t capacity=0, bint with_lock=True):
        """Manually extend the allocator with a new page."""
        if not self.ctx:
            raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
        cdef pthread_mutex_t* lock = &self.ctx.shm_allocator.lock if with_lock else NULL
        cdef nt_shm_page_ctx* page = c_nt_shm_allocator_extend(
            self.ctx, capacity, lock,
        )
        if not page:
            raise OSError(
                errno,
                f"<{self.__class__.__name__}> failed to extend new page",
            )
        return {
            "capacity": <size_t>page.shm_page.capacity,
            "occupied": <size_t>page.shm_page.occupied,
            "name": PyUnicode_FromString(page.shm_page.shm_name),
        }

    # -- Scanning / housekeeping ---------------------------------------------

    def dangling(self, str shm_prefix=None):
        """List allocator SHM objects whose creating process is dead."""
        cdef char out[AP_SHM_NAME_LEN]
        cdef const char* prefix = (
            PyUnicode_AsUTF8(shm_prefix) if shm_prefix else NULL
        )
        cdef nt_shm_allocator* found = c_nt_shm_allocator_dangling(prefix, out)
        if found:
            return [PyUnicode_FromString(out)]
        return []

    def cleanup_dangling(self, str shm_prefix=None):
        """Unlink all dangling allocator/page SHM objects."""
        c_nt_shm_clear_dangling(
            PyUnicode_AsUTF8(shm_prefix) if shm_prefix else NULL
        )

    # -- Properties ----------------------------------------------------------

    property name:
        def __get__(self) -> str:
            if not self.ctx or not self.ctx.shm_allocator:
                return None
            return PyUnicode_FromString(self.ctx.shm_allocator.shm_name)

    property pid:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                return -1
            return <DWORD>self.ctx.shm_allocator.pid

    property mapped_size:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                return -1
            return <size_t>self.ctx.shm_allocator.mapped_size

    property mapped_pages:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                return -1
            return <size_t>self.ctx.shm_allocator.mapped_pages

    property autopage_capacity:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            return <size_t>self.ctx.shm_allocator.autopage_capacity

        def __set__(self, size_t value):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            self.ctx.shm_allocator.autopage_capacity = value

    property autopage_capacity_max:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            return <size_t>self.ctx.shm_allocator.autopage_capacity_max

        def __set__(self, size_t value):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            self.ctx.shm_allocator.autopage_capacity_max = value

    property autopage_alignment:
        def __get__(self):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            return <size_t>self.ctx.shm_allocator.autopage_alignment

        def __set__(self, size_t value):
            if not self.ctx or not self.ctx.shm_allocator:
                raise RuntimeError(f"Uninitialized <{self.__class__.__name__}>")
            self.ctx.shm_allocator.autopage_alignment = value

    property shm_prefix:
        def __get__(self) -> str:
            if not self.ctx or not self.ctx.shm_allocator:
                return None
            return PyUnicode_FromString(self.ctx.shm_allocator.shm_prefix)


# -- Module-level constant exports -------------------------------------------

globals()['AP_SHM_AUTOPAGE_CAPACITY'] = AP_SHM_AUTOPAGE_CAPACITY
globals()['AP_SHM_AUTOPAGE_CAPACITY_MAX'] = AP_SHM_AUTOPAGE_CAPACITY_MAX
globals()['AP_SHM_AUTOPAGE_ALIGNMENT'] = AP_SHM_AUTOPAGE_ALIGNMENT
globals()['AP_SHM_ALLOCATOR_PREFIX'] = PyUnicode_FromString(AP_SHM_ALLOCATOR_PREFIX)
globals()['AP_SHM_NAME_LEN'] = AP_SHM_NAME_LEN
globals()['AP_SHM_PREFIX_MAX'] = AP_SHM_PREFIX_MAX
globals()['AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE'] = AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE
