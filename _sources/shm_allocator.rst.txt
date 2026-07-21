Shared-Memory Allocator
========================

Module: ``cbase.allocator_protocol.c_shm_allocator`` (POSIX)
Module: ``cbase.allocator_protocol.c_nt_shm_allocator`` (Windows)

A POSIX shared-memory backed page allocator that maps pages into a
reserved virtual address region, enabling **cross-process pointer
stability** — pointers within the region are valid across ``fork()``
and independent processes.

The allocator:

- Creates named ``shm_open`` objects and maps them into a reserved
  virtual address region.
- By default reserves **128 GiB** of virtual address space for page
  mappings.
- Uses fixed-address mapping so pages land at stable addresses across
  processes.
- Is POSIX-only (Linux, macOS). On Windows, a limited NT compat layer
  is provided.

.. automodule:: cbase.allocator_protocol.c_shm_allocator
   :members:
   :undoc-members:
   :show-inheritance:

Compile-Time Constants
----------------------

.. code-block:: python

   from cbase.allocator_protocol.c_shm_allocator import (
       AP_SHM_AUTOPAGE_CAPACITY,             # 64 KiB — first/auto page size
       AP_SHM_AUTOPAGE_CAPACITY_MAX,         # 16 MiB — maximum page size
       AP_SHM_AUTOPAGE_ALIGNMENT,            # 4 KiB — page alignment
       AP_SHM_ALLOCATOR_PREFIX,              # "/c_cbase_shm" — default SHM prefix
       AP_SHM_NAME_LEN,                      # 256 — max SHM name length
       AP_SHM_PREFIX_MAX,                    # 64 — max custom prefix length
       AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE, # 128 GiB — default region size
   )

Naming Convention
-----------------

SHM objects follow a naming scheme based on the creator PID:

- Allocator SHM objects: ``/c_cbase_shm_ac_<pid>_<hash>``
- Page SHM objects: ``/c_cbase_shm_pg_<pid>_<index>``

Usage Examples
--------------

Creating and using a shared-memory allocator:

.. code-block:: python

   from cbase.allocator_protocol.c_shm_allocator import SharedMemoryAllocator

   # Create with default 128 GiB region
   alloc = SharedMemoryAllocator()

   # Or with custom region size and SHM prefix
   alloc = SharedMemoryAllocator(region_size=64 << 30, shm_prefix="/my_app_shm")

   # Extend with a default-sized page
   page = alloc.extend()

   # Allocate zeroed memory
   block = alloc.calloc(4096)
   buf = block.buffer  # memoryview

   # Free and reclaim
   alloc.free(block)
   alloc.reclaim()

Cross-Process Sharing
~~~~~~~~~~~~~~~~~~~~~

The allocator is designed for ``fork()``-based multi-process setups:

.. code-block:: python

   import os
   from cbase.allocator_protocol.c_shm_allocator import SharedMemoryAllocator

   alloc = SharedMemoryAllocator()

   # Parent allocates
   block1 = alloc.calloc(1024)
   buf1 = block1.buffer
   buf1[0] = 42

   pid = os.fork()
   if pid == 0:
       # Child — same addresses, same data
       assert buf1[0] == 42
       buf1[0] = 99  # Visible to parent through shared memory
   else:
       os.waitpid(pid, 0)
       assert buf1[0] == 99

Dangling SHM Cleanup
~~~~~~~~~~~~~~~~~~~~

Orphaned SHM objects from crashed processes can be listed and cleaned up:

.. code-block:: python

   # List dangling allocator SHM names
   dead = alloc.dangling()
   print(dead)

   # List dangling page SHM names
   dead_pages = alloc.dangling_pages()

   # Clean up all dangling objects
   alloc.cleanup_dangling()

   # Or target a specific prefix
   alloc.cleanup_dangling(shm_prefix="/my_custom_prefix")

Extracting Creator PID from SHM Names
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   pid = SharedMemoryAllocator.get_pid("/c_cbase_shm_ac_12345_7f...")
   print(pid)  # 12345

.. note::

   The Windows implementation (``NtSharedMemoryAllocator``) provides a
   limited subset of functionality and does not support cross-process
   pointer stability.

.. seealso::

   - :doc:`allocator_protocol` — The pluggable protocol that selects backends
   - :doc:`heap_allocator` — In-process heap allocator
