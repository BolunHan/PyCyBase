Heap Allocator
==============

Module: ``cbase.allocator_protocol.c_heap_allocator``

In-process heap allocator with free-list reuse and auto-growing pages.
Backed by ``malloc`` / ``free`` and managed through a page-list
structure. Thread-safety is achieved via an optional global mutex.

.. automodule:: cbase.allocator_protocol.c_heap_allocator
   :members:
   :undoc-members:
   :show-inheritance:

Module Singleton
----------------

.. code-block:: python

   from cbase.allocator_protocol.c_heap_allocator import ALLOCATOR

``ALLOCATOR`` is a module-level ``HeapAllocator`` instance that serves
as the global heap backend for the allocator protocol.

Compile-Time Constants
----------------------

Auto-page sizing:

.. code-block:: python

   from cbase.allocator_protocol.c_heap_allocator import (
       DEFAULT_AUTOPAGE_CAPACITY,    # 64 KiB — first/auto page size
       MAX_AUTOPAGE_CAPACITY,         # 16 MiB — maximum page size
       DEFAULT_AUTOPAGE_ALIGNMENT,    # 4 KiB — page alignment
   )

Size-binned free-list tuning (added in v0.1.9):

.. code-block:: python

   from cbase.allocator_protocol.c_heap_allocator import (
       EXACT_BIN_COUNT,              # 8192 — exact 8-byte-granular bins (≤ 64 KiB)
       LARGE_BIN_COUNT,              # 9 — pow2-class bins (> 64 KiB)
       BIN_COUNT,                    # 8202 — total bin count (EXACT + LARGE + 1)
       PAGE_EXTEND_MAX,              # 128 MiB — max auto-page extension
       PAGE_FIT_TO_REQUEST,          # 0 — when 1, page fits request instead of pow2 scaling
       EXACT_BIN_PROBE_COUNT,        # 2 — exact bins to probe on miss before page path
   )

Bin-computation helpers (static inline C functions exposed to Cython):

.. code-block:: python

   from cbase.allocator_protocol.c_heap_allocator import (
       c_heap_block_ceil_log2,       # ceil(log2(v)) for bin indexing
       c_heap_block_bin,             # bin index for a given block capacity
   )

Usage Examples
--------------

Direct allocator usage:

.. code-block:: python

   from cbase.allocator_protocol.c_heap_allocator import HeapAllocator

   alloc = HeapAllocator()

   # Extend with a default-sized page
   page = alloc.extend()

   # Allocate zeroed memory (auto-extends as needed)
   block = alloc.calloc(1024)
   buf = block.buffer  # memoryview of the payload

   # Free a block
   alloc.free(block)

   # Reclaim freed space
   alloc.reclaim()

Iterating pages and blocks:

.. code-block:: python

   # All pages, newest-first
   for page in alloc.pages():
       print(f"Page {page.address}: {page.occupied}/{page.capacity}")

   # All allocated blocks
   for block in alloc.allocated():
       print(f"Block {block.address}: {block.size} bytes")

Tuning auto-page parameters:

.. code-block:: python

   alloc.autopage_capacity = 128 * 1024       # 128 KiB
   alloc.autopage_capacity_max = 64 * 1024 * 1024  # 64 MiB
   alloc.autopage_alignment = 4096            # 4 KiB

Thread Safety
-------------

All methods accept a ``with_lock`` parameter (default ``True``).
Set to ``False`` when the caller already holds the lock or when the
allocator is used from a single thread.
