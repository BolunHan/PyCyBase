from collections.abc import Generator
from typing import Any


class InternString:
    """A view into an interned string entry owned by an ``InternStringPool``.

    Each ``InternString`` holds a reference to its parent pool and a
    pointer to the underlying C string buffer.  Two ``InternString``
    instances compare equal when their string values are equal, even if
    they belong to different pools.

    Attributes:
        pool: The ``InternStringPool`` that owns this interned entry.
        hash_value: The raw 64-bit FNV-1a hash stored for this key.
        address: Hex string of the underlying C pointer, or ``None``.
        string: The Python ``str`` content of the interned entry.
    """

    pool: InternStringPool
    """The ``InternStringPool`` that owns this interned entry."""

    hash_value: int
    """The raw 64-bit FNV-1a hash stored for this key (read-only)."""

    address: str | None
    """Hex string of the underlying C pointer (e.g. ``'0x7f...'``), or ``None`` if uninitialized."""

    string: str
    """The Python ``str`` content of this interned entry.

    Raises:
        RuntimeError: If the view is uninitialized.
    """

    def __gt__(self, other: object) -> bool:
        """Return ``True`` if this interned string is greater than *other*.

        Supports comparison with another ``InternString`` or a plain
        Python ``str``.
        """
        ...

    def __eq__(self, other: object) -> bool:
        """Return ``True`` if *other* has the same string value.

        Supports comparison with another ``InternString`` or a plain
        Python ``str``.  Cross-pool comparisons compare by value.
        """
        ...

    def __hash__(self) -> int:
        """Return the cached hash value truncated to signed 64-bit range.

        The underlying hash is a full 64-bit FNV-1a; this accessor
        masks to the low 63 bits for compatibility with Python's
        ``Py_hash_t`` slot.  Suitable for use in dicts and sets.
        """
        ...

    def __repr__(self) -> str:
        """Return a short representation showing the class name and string value.

        Uninitialized instances show ``'(uninitialized)'``.
        """
        ...


class InternStringPool:
    """A thread-safe hash map that interns (deduplicates) strings.

    Strings are stored as NUL-terminated UTF-8 in memory backed by the
    module's allocator protocol.  Each unique key is stored exactly once;
    subsequent ``istr()`` calls return the same ``InternString`` view.

    ``InternStringPool()`` creates a pool with the default allocator
    (SHM-backed, locked, freelist-enabled).  Module-level singletons
    ``POOL`` (SHM) and ``INTRA_POOL`` (heap) are also available.

    Attributes:
        size: Number of unique interned strings (same as ``len(pool)``).
        address: Hex string of the underlying C ``istr_map`` pointer, or ``None``.
    """

    size: int
    """The number of unique interned strings in the pool."""

    address: str | None
    """Hex string of the underlying C ``istr_map`` pointer, or ``None``."""

    def __init__(self) -> None:
        """Create an empty pool backed by the default allocator.

        The default allocator is SHM-backed with locking and freelist
        enabled, suitable for cross-process sharing.
        """
        ...

    def __len__(self) -> int:
        """Return the number of unique interned strings (same as :attr:`size`)."""
        ...

    def __getitem__(self, key: str) -> InternString:
        """Return an ``InternString`` view for *key*.

        Args:
            key: The string to look up.

        Returns:
            An ``InternString`` wrapping the interned entry.

        Raises:
            KeyError: If *key* has not been interned in this pool.
        """
        ...

    def __contains__(self, key: str) -> bool:
        """Return ``True`` if *key* is interned in this pool.

        Delegates to ``c_istr_map_lookup_synced`` — a pure read-only
        lookup with no side effects.  Returns ``False`` for missing
        keys instead of raising :exc:`KeyError` like :meth:`__getitem__`
        does.
        """
        ...

    def istr(self, string: str) -> InternString:
        """Intern (or look up) *string* and return an ``InternString`` view.

        If *string* is already in the pool the existing entry is
        returned; otherwise it is interned (copied into pool memory).

        Args:
            string: The Python ``str`` to intern.

        Returns:
            An ``InternString`` wrapping the interned entry.

        Raises:
            MemoryError: If allocation fails.
        """
        ...

    def internalized(self) -> Generator[InternString, None, None]:
        """Yield all interned entries as ``InternString`` views.

        Iteration order is reverse insertion order (LIFO linked list).
        Re-interning an existing key does not change its position.

        Yields:
            ``InternString`` instances for every entry in the pool.
        """
        ...


class IstrTestToolkit:
    """Performance benchmark toolkit for ``InternString`` vs Python ``str``.

    Generates a large shared character buffer, segments it into
    random-length strings, then benchmarks C-level hash / intern /
    lookup / equality against equivalent Python ``str`` operations.

    Attributes:
        buf_size: Size of the character buffer in bytes.
        n_seg: Number of random segments generated.
        max_seg_len: Maximum length of each random segment in bytes.
        n_iters: Number of benchmark iterations.
        n_unique: Number of unique strings in the limited-pool subset.
        n_ops: Number of operations per limited-pool iteration.
        pool: An ``InternStringPool`` pre-populated with all segments.
    """

    buf_size: int
    """Size of the character buffer in bytes."""

    n_seg: int
    """Number of random segments generated."""

    max_seg_len: int
    """Maximum length of each random segment in bytes."""

    n_iters: int
    """Number of benchmark iterations per routine."""

    n_unique: int
    """Number of unique strings in the limited-pool subset."""

    n_ops: int
    """Number of operations per limited-pool iteration."""

    pool: InternStringPool
    """An ``InternStringPool`` pre-populated with all segments for warm-up."""

    def __init__(
        self,
        buf_size: int = 2**30,
        n_seg: int = 100_000,
        max_seg_len: int = 64,
        n_iters: int = 10,
        n_unique: int = 0,
        n_ops: int = 0,
    ) -> None:
        """Create a benchmark toolkit with random reproducible data.

        Args:
            buf_size: Size of the character buffer in bytes (default 1 GiB).
            n_seg: Number of random segments to generate (default 100 000).
            max_seg_len: Maximum segment length in bytes (default 64).
            n_iters: Number of benchmark iterations (default 10).
            n_unique: Unique strings for limited-pool benchmarks
                (default ``max(n_seg // 10, 1)``).
            n_ops: Operations per limited-pool iteration (default *n_seg*).

        Raises:
            ValueError: If parameters are inconsistent.
            MemoryError: If buffer or segment array allocation fails.
        """
        ...

    def istr_hash_routine(self) -> float:
        """Benchmark FNV-1a hash at C level (no allocation).

        Returns:
            Total elapsed time in seconds across all iterations.
        """
        ...

    def istr_intern_routine(self) -> float:
        """Benchmark ``c_istr`` intern (all-miss, unlocked).

        Creates a fresh pool per iteration.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_intern_synced_routine(self) -> float:
        """Benchmark ``c_istr_synced`` intern (all-miss, locked).

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_lookup_routine(self) -> float:
        """Benchmark ``c_istr_map_lookup`` (all-hits, unlocked).

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_lookup_synced_routine(self) -> float:
        """Benchmark ``c_istr_map_lookup_synced`` (all-hits, locked).

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_eq_routine(self) -> float:
        """Benchmark ``InternString`` Python-level equality.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def py_unicode_routine(self) -> float:
        """Benchmark Python ``str`` creation from raw bytes.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def py_hash_routine(self) -> float:
        """Benchmark Python ``hash()`` on all segments.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def py_eq_routine(self) -> float:
        """Benchmark Python ``str`` equality.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_limited_pool_routine(self) -> float:
        """Benchmark intern with limited unique pool (hit-heavy, unlocked).

        Each iteration picks *n_ops* random strings (with replacement)
        from *n_unique* segments.  Most operations are hits.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_limited_pool_synced_routine(self) -> float:
        """Same as :meth:`istr_limited_pool_routine` but locked.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def py_unicode_limited_routine(self) -> float:
        """Benchmark Python ``str`` creation from limited-pool picks.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def istr_miss_rate_routine(self, miss_rate: float) -> float:
        """Benchmark intern with a controlled miss rate (unlocked).

        Args:
            miss_rate: Fraction of operations that are misses, in (0, 1].
                e.g. 0.001 → 1/1K, 0.0001 → 1/10K.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def py_unicode_miss_rate_routine(self, miss_rate: float) -> float:
        """Benchmark Python ``str`` creation with a controlled miss rate.

        Args:
            miss_rate: Same semantics as :meth:`istr_miss_rate_routine`.

        Returns:
            Total elapsed time in seconds.
        """
        ...

    def run_test(self) -> dict[str, Any]:
        """Run all benchmarks and return a dictionary of results.

        Returns:
            A dict with per-operation nanosecond averages
            (``'_ns'`` keys) and raw timings in seconds (``'_s'`` keys),
            plus metadata keys (``buf_size``, ``n_seg``, etc.).
        """
        ...


# Module-level singletons

POOL: InternStringPool
"""The global SHM-backed ``InternStringPool`` for cross-process sharing.

Backed by ``AP_SHM_ALLOCATOR`` — child processes inherit the shared
memory mapping and see all entries regardless of when they were interned.
"""

INTRA_POOL: InternStringPool
"""The global heap-backed ``InternStringPool`` for intra-process use.

Backed by ``AP_HEAP_ALLOCATOR``.  After ``fork()`` the child sees a
COW copy of pre-fork entries but post-fork insertions are isolated to
each process.
"""

C_POOL: int
"""Raw pointer (``uintptr_t``) to the C ``istr_map`` backing ``POOL``."""

C_INTRA_POOL: int
"""Raw pointer (``uintptr_t``) to the C ``istr_map`` backing ``INTRA_POOL``."""
