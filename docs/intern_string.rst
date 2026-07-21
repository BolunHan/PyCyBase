Intern String
==============

Module: ``cbase.intern_string``

A thread-safe string interning system backed by the allocator protocol.
Strings are stored as NUL-terminated UTF-8 in memory, with FNV-1a
hashing and cached hash values for fast comparisons.

Key benefits over Python ``str``:

- **String deduplication** — same pointer for the same key
- **Stable C pointer** — ``const char*`` usable as a hash key
- **Cached 64-bit FNV-1a hash** — no re-computation on ``hash()``
- **Cross-process sharing** — SHM-backed pools are visible after ``fork()``

Benchmarks show **1.7–2.2× speedup** over Python ``str`` creation with
typical miss rates (1/1,000 to 1/1,000,000).

.. automodule:: cbase.intern_string.c_intern_string
   :members:
   :undoc-members:
   :show-inheritance:

Module Singletons
-----------------

.. code-block:: python

   from cbase.intern_string import POOL, INTRA_POOL, C_POOL, C_INTRA_POOL

- ``POOL`` — SHM-backed pool for cross-process sharing. After ``fork()``,
  the child process sees all entries regardless of when they were interned.
- ``INTRA_POOL`` — Heap-backed pool for intra-process use. After ``fork()``,
  the child sees a COW copy of pre-fork entries, but post-fork insertions
  are isolated to each process.
- ``C_POOL`` / ``C_INTRA_POOL`` — Raw ``uintptr_t`` pointers to the
  underlying C ``istr_map`` structures.

Usage Examples
--------------

Basic interning:

.. code-block:: python

   from cbase.intern_string import POOL

   # Intern a string (returns an InternString view)
   aapl = POOL.istr("AAPL")
   tsla = POOL.istr("TSLA")

   # Same string → same view
   aapl_again = POOL.istr("AAPL")
   assert aapl is aapl_again  # Identity!

   # Comparison
   assert aapl != tsla
   assert aapl == "AAPL"  # Compares to plain str

   # Hash for dict/set use
   tickers = {aapl, tsla}

   # Access properties
   print(aapl.string)      # "AAPL"
   print(aapl.hash_value)  # 64-bit FNV-1a hash
   print(aapl.address)     # Hex C pointer, e.g. "0x7f..."

Pool membership:

.. code-block:: python

   pool = POOL

   # Check membership (no side effects)
   assert "AAPL" in pool
   assert "UNKNOWN" not in pool

   # Direct lookup (raises KeyError if missing)
   view = pool["AAPL"]

   # Pool size
   print(len(pool))  # Number of interned strings

   # Iterate all entries (reverse insertion order)
   for istring in pool.internalized():
       print(istring.string)

Custom pool:

.. code-block:: python

   from cbase.intern_string import InternStringPool

   # Creates a new pool with default allocator (SHM-backed)
   local = InternStringPool()
   local.istr("hello")

Benchmark Toolkit
~~~~~~~~~~~~~~~~~

Run comprehensive benchmarks:

.. code-block:: python

   from cbase.intern_string import IstrTestToolkit

   toolkit = IstrTestToolkit(buf_size=2**30, n_seg=100_000)
   results = toolkit.run_test()

   for k, v in results.items():
       if k.endswith("_ns"):
           print(f"{k}: {v:.1f} ns")

Cross-Process Usage
-------------------

.. code-block:: python

   import os
   from cbase.intern_string import POOL

   POOL.istr("shared_data")
   print(len(POOL))  # e.g., 1

   pid = os.fork()
   if pid == 0:
       # Child: sees all pre-fork entries
       print(len(POOL))         # 1
       print("shared_data" in POOL)  # True

       # Insertions in child are visible to parent (SHM-backed)
       POOL.istr("child_data")
   else:
       os.waitpid(pid, 0)
       print("child_data" in POOL)  # True — SHM-backed

.. seealso::

   - :doc:`allocator_protocol` — The allocator backing the string pool
   - :doc:`bytemap` — Fast hash maps for byte-string keys
   - ``cbase/intern_string/BENCHMARK.md`` — Detailed benchmark results
