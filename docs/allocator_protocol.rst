Allocator Protocol
==================

The allocator protocol is the central abstraction of PyCyBase — a
pluggable memory allocation layer that dispatches to heap, shared-memory
(SHM), or raw ``malloc`` backends based on global environment settings.

Module: ``cbase.allocator_protocol``

.. automodule:: cbase.allocator_protocol
   :members:
   :undoc-members:
   :show-inheritance:

Configuration Contexts
----------------------

The ``AllocatorConfigContext`` extends :doc:`EnvConfigContext <env_config>` to
dispatch configuration changes to the underlying heap and shared-memory
allocators. Accepted keyword arguments:

.. list-table::
   :header-rows: 1

   * - Key
     - Type
     - Description
   * - ``locked``
     - ``bool``
     - Enable/disable mutex locking for thread safety
   * - ``shared``
     - ``bool``
     - Enable/disable shared memory allocation
   * - ``freelist``
     - ``bool``
     - Enable/disable free-list reuse
   * - ``autopage_capacity``
     - ``int``
     - Propagated to both heap and SHM allocators
   * - ``autopage_capacity_max``
     - ``int``
     - Propagated to both heap and SHM allocators
   * - ``autopage_alignment``
     - ``int``
     - Propagated to both heap and SHM allocators

Sentinel Contexts
-----------------

The module exports pre-configured context instances for common use:

.. code-block:: python

   from cbase.allocator_protocol import AP_SHARED, AP_LOCKED, AP_LOCKFREE, AP_FREELIST

- ``AP_SHARED`` — enable shared-memory allocation
- ``AP_LOCKED`` — enable thread-safety locking
- ``AP_LOCKFREE`` — disable thread-safety locking
- ``AP_FREELIST`` — enable free-list reuse (no effect in SHM mode)

Usage Examples
--------------

Basic allocation with the default allocator (SHM-backed):

.. code-block:: python

   from cbase.allocator_protocol import AllocatorProtocol, AP_SHARED

   with AP_SHARED:
       alloc = AllocatorProtocol(1024)
       alloc.buf[0] = b'x'
       print(f"size={alloc.size}, with_shm={alloc.with_shm}")

Composing contexts with ``|``:

.. code-block:: python

   from cbase.allocator_protocol import AP_SHARED, AP_LOCKED, AP_FREELIST

   # SHM + thread-safe + freelist
   ctx = AP_SHARED | AP_LOCKED | AP_FREELIST

   with ctx:
       alloc = AllocatorProtocol(4096)
       # ... use alloc ...

Inverting a context with ``~`` to disable a flag:

.. code-block:: python

   unlocked = ~AP_LOCKED  # disables locking

Using as a decorator:

.. code-block:: python

   @AP_SHARED
   def allocate_shared():
       return AllocatorProtocol(2048)

Under the Hood
--------------

The module maintains three global allocator schematics (C structs) that
define the default, SHM-only, and heap-only configurations:

- ``AP_DEFAULT_ALLOCATOR`` — SHM-backed, locked, freelist-enabled
- ``AP_SHM_ALLOCATOR`` — SHM-backed, locked, freelist-enabled, no heap
- ``AP_HEAP_ALLOCATOR`` — heap-backed, locked, freelist-enabled, no SHM

``AllocatorProtocol(size)`` checks ``AP_DEFAULT_ALLOCATOR.with_shm`` at
construction time and selects the appropriate backend.

.. seealso::

   - :doc:`heap_allocator` — In-process heap allocator details
   - :doc:`shm_allocator` — Shared-memory allocator details
   - :doc:`env_config` — Base ``EnvConfigContext`` class
