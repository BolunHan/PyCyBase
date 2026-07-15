from cpython.unicode cimport PyUnicode_AsUTF8AndSize, PyUnicode_FromString
from libc.stdint cimport uintptr_t
from libc.stdlib cimport free, calloc

from cbase.allocator_protocol.c_allocator_protocol cimport AP_DEFAULT_ALLOCATOR, AP_SHM_ALLOCATOR, AP_HEAP_ALLOCATOR


cdef class InternString:
    @staticmethod
    cdef InternString c_from_entry(const istr_entry* entry, InternStringPool parent_pool):
        cdef InternString instance = InternString.__new__(InternString)
        instance.pool = parent_pool
        instance.key = <const char*> entry.key
        instance.hash = entry.hash
        return instance

    def __gt__(self, object other):
        if isinstance(other, InternString):
            return self.string.__gt__(other.string)
        return self.string.__gt__(other)

    def __eq__(self, object other):
        if isinstance(other, InternString):
            return self.string.__eq__(other.string)
        return self.string.__eq__(other)

    def __hash__(self):
        # Truncate to signed 64-bit range for Cython's tp_hash slot.
        # Cython extension types route __hash__ through the C-level
        # Py_hash_t slot which requires Py_ssize_t compatibility.
        # The raw uint64_t hash can overflow this; masking keeps the
        # low 63 bits, which is sufficient for hash tables and
        # matches Python's own hash() truncation behaviour.
        return self.hash & 0x7FFFFFFFFFFFFFFF

    def __repr__(self):
        if self.key:
            return f'<{self.__class__.__name__}>({PyUnicode_FromString(self.key)})>'
        return f'<{self.__class__.__name__}>(uninitialized)>'

    property string:
        def __get__(self):
            if self.key:
                return PyUnicode_FromString(self.key)
            raise RuntimeError('Not initialized')

    property hash_value:
        def __get__(self):
            if self.hash:
                return self.hash

    property address:
        def __get__(self):
            if self.key:
                return f'{<uintptr_t> self.key:#0x}'
            return None


cdef class InternStringPool:
    def __init__(self):
        self.pool = c_istr_map_new(0, AP_DEFAULT_ALLOCATOR)
        self.owner = True

    def __dealloc__(self):
        if not self.owner:
            return

        if self.pool:
            c_istr_map_free(self.pool)

    @staticmethod
    cdef InternStringPool c_from_header(const istr_map* header, bint owner=False):
        cdef InternStringPool instance = InternStringPool.__new__(InternStringPool)
        instance.pool = <istr_map*> header
        instance.owner = owner
        return instance

    def __len__(self):
        if not self.pool:
            raise RuntimeError(f'<{self.__class__.__name__}> Not properly initialized! Missing istr_map header!')
        return istr_map_size(self.pool)

    def __getitem__(self, str key):
        cdef Py_ssize_t key_length = 0
        cdef const char* utf8_string = PyUnicode_AsUTF8AndSize(key, &key_length)
        cdef const istr_entry* entry = c_istr_map_lookup_synced(self.pool, utf8_string, <size_t> key_length)
        if not entry:
            raise KeyError(f'{key} not interned')
        return InternString.c_from_entry(entry, self)

    cpdef InternString istr(self, str string):
        cdef Py_ssize_t key_length = 0
        cdef const char* utf8_string = PyUnicode_AsUTF8AndSize(string, &key_length)
        cdef const istr_entry* out_entry = NULL
        cdef const char* istr = c_istr_synced(self.pool, utf8_string, <size_t> key_length, &out_entry)
        if not istr:
            raise MemoryError('Failed to intern string.')
        return InternString.c_from_entry(out_entry, self)

    def internalized(self):
        cdef istr_entry* entry = istr_map_first(self.pool)
        while entry:
            yield InternString.c_from_entry(entry, self)
            entry = entry.next

    property size:
        def __get__(self):
            if self.pool:
                return istr_map_size(self.pool)
            raise RuntimeError('Not initialized')

    property address:
        def __get__(self):
            if self.pool:
                return f'{<uintptr_t> self.pool:#0x}'
            return None


cdef class IstrTestToolkit:
    """Performance benchmark toolkit for InternString vs Python str.

    Generates a large shared character buffer, segments it into random-length
    strings, then benchmarks C-level hash / intern / lookup / equality against
    equivalent Python str operations.

    Parameters
    ----------
    buf_size : size_t
        Size of the character buffer in bytes (default 2^30 ≈ 1 GiB).
    n_seg : size_t
        Number of segments to generate (default 100_000).
    max_seg_len : size_t
        Maximum length of each random segment in bytes (default 64).
    n_iters : size_t
        Number of benchmark iterations (default 10).
    """

    def __cinit__(self, size_t buf_size=2**30, size_t n_seg=100_000,
                  size_t max_seg_len=64, size_t n_iters=10):
        from random import seed, randint
        cdef size_t i

        if max_seg_len < 1 or max_seg_len > buf_size // n_seg:
            raise ValueError(f'Invalid max_seg_len={max_seg_len} for '
                             f'buf_size={buf_size}, n_seg={n_seg}')
        if n_seg == 0 or buf_size == 0 or n_iters == 0:
            raise ValueError('buf_size, n_seg, n_iters must be > 0')

        self.buf_size = buf_size
        self.n_seg = n_seg
        self.max_seg_len = max_seg_len
        self.n_iters = n_iters

        # Allocate the character buffer (1 extra byte for NUL safety)
        self.buf = <char*> calloc(buf_size + 1, 1)
        if self.buf == NULL:
            raise MemoryError(f'Failed to allocate buf of size {buf_size}')

        # Allocate segment arrays
        self.seg_offsets = <size_t*> calloc(n_seg, sizeof(size_t))
        self.seg_lengths = <size_t*> calloc(n_seg, sizeof(size_t))
        self.c_keys = <const char**> calloc(n_seg, sizeof(const char*))
        self.c_key_lens = <size_t*> calloc(n_seg, sizeof(size_t))
        if (self.seg_offsets == NULL or self.seg_lengths == NULL or
            self.c_keys == NULL or self.c_key_lens == NULL):
            raise MemoryError(f'Failed to allocate segment arrays for n_seg={n_seg}')

        # Fill buffer and generate segments
        seed(42)  # reproducible
        self.c_gen_buf()
        self.c_gen_segments()

        # Prepare Python objects and intern pool
        self.py_strings = []
        self.py_bytes_list = []
        self.pool = InternStringPool()
        self.c_prepare_py_objects()
        self.c_prepare_istr_pool()

    def __dealloc__(self):
        if self.buf != NULL:
            free(self.buf)
            self.buf = NULL
        if self.seg_offsets != NULL:
            free(self.seg_offsets)
            self.seg_offsets = NULL
        if self.seg_lengths != NULL:
            free(self.seg_lengths)
            self.seg_lengths = NULL
        if self.c_keys != NULL:
            free(self.c_keys)
            self.c_keys = NULL
        if self.c_key_lens != NULL:
            free(self.c_key_lens)
            self.c_key_lens = NULL

    # ------------------------------------------------------------------
    #  Setup helpers
    # ------------------------------------------------------------------

    cdef inline void c_gen_buf(self):
        """Fill buf with random printable ASCII characters."""
        from random import randint
        cdef size_t i
        for i in range(self.buf_size):
            self.buf[i] = <char> randint(33, 126)  # printable ASCII

    cdef inline void c_gen_segments(self):
        """Generate random non-overlapping offsets and lengths within buf."""
        from random import randint
        cdef size_t i, offset, length
        cdef size_t stride = self.buf_size // self.n_seg
        cdef size_t half_stride = stride // 2
        cdef size_t half_max = self.max_seg_len // 2
        if half_max < 1:
            half_max = 1

        for i in range(self.n_seg):
            # Base position within the i-th stride
            offset = i * stride
            # Add random jitter so segments aren't perfectly aligned
            offset += <size_t> randint(1, <int> half_stride)
            if offset + self.max_seg_len > self.buf_size:
                offset = self.buf_size - self.max_seg_len
            length = <size_t> randint(1, <int> self.max_seg_len)
            self.seg_offsets[i] = offset
            self.seg_lengths[i] = length
            self.c_keys[i] = self.buf + offset
            self.c_key_lens[i] = length

    cdef inline void c_prepare_py_objects(self):
        """Create Python str and bytes objects from every segment."""
        cdef size_t i
        cdef bytes b
        self.py_strings = []
        self.py_bytes_list = []
        for i in range(self.n_seg):
            b = self.buf[self.seg_offsets[i]:self.seg_offsets[i] + self.seg_lengths[i]]
            self.py_bytes_list.append(b)
            self.py_strings.append(b.decode('ascii'))

    cdef inline void c_prepare_istr_pool(self):
        """Intern every segment into the pool via Python str (warm-up)."""
        cdef size_t i
        for i in range(self.n_seg):
            self.pool.istr(self.py_strings[i])

    # ------------------------------------------------------------------
    #  C-level hash benchmark (fnv1a_hash)
    # ------------------------------------------------------------------

    cpdef double istr_hash_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef uint64_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg):
                checksum += fnv1a_hash(self.c_keys[i], self.c_key_lens[i])
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Intern benchmark — pure C-level, unlocked
    # ------------------------------------------------------------------

    cpdef double istr_intern_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef istr_map* cmap
        cdef const istr_entry* entry
        cdef uintptr_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            cmap = c_istr_map_new(0, AP_DEFAULT_ALLOCATOR)
            if cmap == NULL:
                raise MemoryError('c_istr_map_new failed')
            start_ts = perf_counter()
            for i in range(self.n_seg):
                c_istr(cmap, self.c_keys[i], self.c_key_lens[i], &entry)
                checksum += <uintptr_t> entry
            elapsed += perf_counter() - start_ts
            c_istr_map_free(cmap)

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Intern benchmark — C-level with mutex (synced)
    # ------------------------------------------------------------------

    cpdef double istr_intern_synced_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef istr_map* cmap
        cdef const istr_entry* entry
        cdef uintptr_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            cmap = c_istr_map_new(0, AP_DEFAULT_ALLOCATOR)
            if cmap == NULL:
                raise MemoryError('c_istr_map_new failed')
            start_ts = perf_counter()
            for i in range(self.n_seg):
                c_istr_synced(cmap, self.c_keys[i], self.c_key_lens[i], &entry)
                checksum += <uintptr_t> entry
            elapsed += perf_counter() - start_ts
            c_istr_map_free(cmap)

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Lookup benchmark — pure C-level, unlocked
    # ------------------------------------------------------------------

    cpdef double istr_lookup_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef const istr_entry* entry
        cdef uintptr_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg):
                entry = c_istr_map_lookup(self.pool.pool, self.c_keys[i], self.c_key_lens[i])
                checksum += <uintptr_t> entry
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Lookup benchmark — C-level with mutex (synced)
    # ------------------------------------------------------------------

    cpdef double istr_lookup_synced_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef const istr_entry* entry
        cdef uintptr_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg):
                entry = c_istr_map_lookup_synced(self.pool.pool, self.c_keys[i], self.c_key_lens[i])
                checksum += <uintptr_t> entry
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Equality benchmark — InternString Python-level eq
    # ------------------------------------------------------------------

    cpdef double istr_eq_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef size_t checksum = 0
        cdef InternString a, b

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg - 1):
                a = self.pool[self.py_strings[i]]
                b = self.pool[self.py_strings[i + 1]]
                if a == b:
                    checksum += 1
                else:
                    checksum += 2
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Python str creation benchmark
    # ------------------------------------------------------------------

    cpdef double py_unicode_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef uintptr_t checksum = 0
        cdef bytes b
        cdef str s

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg):
                b = self.buf[self.seg_offsets[i]:self.seg_offsets[i] + self.seg_lengths[i]]
                s = b.decode('ascii')
                checksum += len(s)
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Python hash benchmark
    # ------------------------------------------------------------------

    cpdef double py_hash_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef uint64_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg):
                checksum += <uint64_t> hash(self.py_strings[i])
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Python equality benchmark
    # ------------------------------------------------------------------

    cpdef double py_eq_routine(self):
        cdef size_t iter_idx, i
        cdef double elapsed = 0.0
        cdef double start_ts
        cdef size_t checksum = 0

        from time import perf_counter
        for iter_idx in range(self.n_iters):
            start_ts = perf_counter()
            for i in range(self.n_seg - 1):
                if self.py_strings[i] == self.py_strings[i + 1]:
                    checksum += 1
                else:
                    checksum += 2
            elapsed += perf_counter() - start_ts

        self.buf[0] = <char> (checksum & 0xFF)
        return elapsed

    # ------------------------------------------------------------------
    #  Run all benchmarks
    # ------------------------------------------------------------------

    cpdef dict run_test(self):
        cdef double istr_hash_t      = self.istr_hash_routine()
        cdef double istr_intern_t    = self.istr_intern_routine()
        cdef double istr_intern_s_t  = self.istr_intern_synced_routine()
        cdef double istr_lookup_t    = self.istr_lookup_routine()
        cdef double istr_lookup_s_t  = self.istr_lookup_synced_routine()
        cdef double istr_eq_t        = self.istr_eq_routine()
        cdef double py_unicode_t     = self.py_unicode_routine()
        cdef double py_hash_t        = self.py_hash_routine()
        cdef double py_eq_t          = self.py_eq_routine()

        cdef size_t total_bytes = 0
        cdef size_t i
        for i in range(self.n_seg):
            total_bytes += self.seg_lengths[i]

        cdef size_t n = self.n_seg
        cdef size_t n_iters = self.n_iters

        return {
            'buf_size': self.buf_size,
            'n_seg': n,
            'max_seg_len': self.max_seg_len,
            'n_iters': n_iters,
            'total_key_bytes': total_bytes,
            # Intern string — C-level (unlocked)
            'istr_hash_ns':         (istr_hash_t     / n_iters / n) * 1e9,
            'istr_intern_ns':       (istr_intern_t   / n_iters / n) * 1e9,
            'istr_intern_synced_ns':(istr_intern_s_t / n_iters / n) * 1e9,
            'istr_lookup_ns':       (istr_lookup_t   / n_iters / n) * 1e9,
            'istr_lookup_synced_ns':(istr_lookup_s_t / n_iters / n) * 1e9,
            'istr_eq_ns':           (istr_eq_t       / n_iters / (n - 1)) * 1e9,
            # Mutex overhead
            'intern_mutex_ns':      ((istr_intern_s_t - istr_intern_t) / n_iters / n) * 1e9,
            'lookup_mutex_ns':      ((istr_lookup_s_t - istr_lookup_t) / n_iters / n) * 1e9,
            # Python benchmarks
            'py_unicode_ns': (py_unicode_t / n_iters / n) * 1e9,
            'py_hash_ns':    (py_hash_t    / n_iters / n) * 1e9,
            'py_eq_ns':      (py_eq_t      / n_iters / (n - 1)) * 1e9,
            # Raw timings
            'istr_hash_s':         istr_hash_t,
            'istr_intern_s':       istr_intern_t,
            'istr_intern_synced_s':istr_intern_s_t,
            'istr_lookup_s':       istr_lookup_t,
            'istr_lookup_synced_s':istr_lookup_s_t,
            'istr_eq_s':           istr_eq_t,
            'py_unicode_s':        py_unicode_t,
            'py_hash_s':           py_hash_t,
            'py_eq_s':             py_eq_t,
        }


# ============================================================
#  Module-level pools
# ============================================================

cdef istr_map* C_POOL = c_istr_map_new(0, AP_SHM_ALLOCATOR)
globals()['C_POOL'] = <uintptr_t> C_POOL
cdef InternStringPool POOL = InternStringPool.c_from_header(C_POOL, True)
globals()['POOL'] = POOL

cdef istr_map* C_INTRA_POOL = c_istr_map_new(0, AP_HEAP_ALLOCATOR)
globals()['C_INTRA_POOL'] = <uintptr_t> C_INTRA_POOL
cdef InternStringPool INTRA_POOL = InternStringPool.c_from_header(C_INTRA_POOL, True)
globals()['INTRA_POOL'] = INTRA_POOL
