C API Reference
===============

This page documents the low-level C API exposed by PyCyBase's header
files. These APIs are used internally by the Cython layer and are
available for downstream extension developers who need direct C-level
access.

.. warning::
   The C API is considered advanced/internal. Most users should use the
   Python APIs documented in the other sections. Direct C API usage
   requires Cython or C extension knowledge.

Overview
--------

PyCyBase's C layer provides:

- **Allocator protocol** — Pluggable allocation dispatch
- **Heap allocator** — Free-list-based page allocator
- **SHM allocator** — POSIX shared-memory page allocator
- **ByteMap** — xxHash3-backed hash maps
- **InternString** — FNV-1a-hashed string interning
- **EnvConfig** — Configuration context management

All C structures are exposed to Python via Cython ``cdef`` classes in
the ``.pyx`` files and declared in ``.pxd`` files for ``cimport``.

Header Files
------------

Headers are located under ``cbase/`` and mirrored into
``cbase/includes/cbase/`` at build time.

c_allocator_protocol.h
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   typedef struct allocator_protocol {
       void*       buf;
       size_t      size;
       bool        with_lock;
       bool        with_shm;
       bool        with_freelist;
       heap_allocator*     heap_allocator;
       shm_allocator_ctx*  shm_allocator_ctx;
       shm_allocator*      shm_allocator;
   } allocator_protocol;

   allocator_protocol* c_ap_allocator_protocol_new(
       size_t size,
       shm_allocator_ctx* shm_ctx,
       heap_allocator* heap_ctx,
       bool with_lock
   );
   void c_ap_allocator_protocol_free(allocator_protocol* protocol);
   void c_ap_allocator_protocol_acquire_owner(allocator_protocol* protocol);
   int c_ap_allocator_protocol_release_owner(allocator_protocol* protocol);

   void* c_ap_alloc(size_t size, allocator_protocol* protocol);
   void c_ap_free(void* ptr, allocator_protocol* protocol);
   void* c_ap_strdup(const char* src, allocator_protocol* protocol);

c_heap_allocator.h
~~~~~~~~~~~~~~~~~~

.. code-block:: c

   typedef struct heap_allocator {
       heap_page*    active_page;
       heap_page*    pages;
       heap_block*   free_list;
       size_t        mapped_pages;
       size_t        autopage_capacity;
       size_t        autopage_capacity_max;
       size_t        autopage_alignment;
       pthread_mutex_t lock;
   } heap_allocator;

   typedef struct heap_page {
       heap_page*    next;
       void*         buffer;
       size_t        capacity;
       size_t        occupied;
       heap_block*   allocated;
   } heap_page;

   typedef struct heap_block {
       heap_page*    parent_page;
       heap_block*   next_free;
       heap_block*   next_allocated;
       size_t        size;
       size_t        capacity;
       void*         padding;  // payload follows header
   } heap_block;

Key functions:

- ``heap_allocator* c_heap_allocator_new()`` — Create allocator
- ``void c_heap_allocator_free(heap_allocator*)`` — Destroy allocator
- ``heap_page* c_heap_allocator_extend(heap_allocator*, size_t, bool)`` — Add page
- ``heap_block* c_heap_calloc(heap_allocator*, size_t, bool)`` — Allocate zeroed
- ``heap_block* c_heap_request(heap_allocator*, size_t, bool, bool)`` — Request block
- ``void c_heap_free(heap_allocator*, heap_block*, bool)`` — Return to free list
- ``void c_heap_reclaim(heap_allocator*, bool)`` — Coalesce free list

c_shm_allocator.h
~~~~~~~~~~~~~~~~~

.. code-block:: c

   typedef struct shm_allocator_ctx {
       shm_allocator*  shm_allocator;
       char            shm_prefix[AP_SHM_PREFIX_MAX];
       char            shm_name[AP_SHM_NAME_LEN];
   } shm_allocator_ctx;

   typedef struct shm_allocator {
       void*           region;
       size_t          region_size;
       size_t          mapped_size;
       shm_page*       pages;
       shm_page*       active_page;
       shm_block*      free_list;
       size_t          mapped_pages;
       pid_t           pid;
       char            shm_name[AP_SHM_NAME_LEN];
       size_t          autopage_capacity;
       size_t          autopage_capacity_max;
       size_t          autopage_alignment;
       pthread_mutex_t lock;
   } shm_allocator;

Key functions:

- ``shm_allocator_ctx* c_shm_allocator_new(size_t, const char*)`` — Create
- ``void c_shm_allocator_free(shm_allocator_ctx*)`` — Destroy
- ``shm_block* c_shm_calloc(shm_allocator_ctx*, size_t, bool)`` — Allocate zeroed
- ``shm_block* c_shm_request(shm_allocator_ctx*, size_t, bool, bool)`` — Request
- ``void c_shm_free(shm_allocator_ctx*, shm_block*, bool)`` — Free
- ``void c_shm_reclaim(shm_allocator_ctx*, bool)`` — Coalesce

c_bytemap.h
~~~~~~~~~~~

.. code-block:: c

   typedef struct bytemap_entry {
       int64_t     hash;
       void*       key;
       size_t      key_len;
       int64_t     seq_id;
   } bytemap_entry;

   typedef struct bytemap {
       bytemap_entry* entries;
       size_t          size;
       size_t          capacity;
       size_t          occupied;
       size_t          salt;
   } bytemap;

Key functions:

- ``bytemap* c_bytemap_new(size_t init_capacity)``
- ``void c_bytemap_free(bytemap*)``
- ``bytemap_entry* c_bytemap_set(bytemap*, void* key, size_t key_len, int64_t hash, void* value)``
- ``bytemap_entry* c_bytemap_get(bytemap*, void* key, size_t key_len, int64_t hash)``
- ``int c_bytemap_contains(bytemap*, void* key, size_t key_len, int64_t hash)``
- ``bytemap_entry* c_bytemap_pop(bytemap*, void* key, size_t key_len, int64_t hash)``

c_intern_string.h
~~~~~~~~~~~~~~~~~

.. code-block:: c

   typedef struct istr_map {
       bytemap*       map;
       intern_entry*  entries;
       size_t         size;
       allocator_protocol* allocator;
       pthread_mutex_t lock;
   } istr_map;

Key functions:

- ``istr_map* c_istr_map_new(allocator_protocol*)``
- ``void c_istr_map_free(istr_map*)``
- ``const char* c_istr(istr_map*, const char*, size_t)`` — Intern (unlocked)
- ``const char* c_istr_synced(istr_map*, const char*, size_t)`` — Intern (locked)

Memory Management
-----------------

Ownership Rules
~~~~~~~~~~~~~~~

1. **Allocator protocol**: Created via ``c_ap_allocator_protocol_new()``,
   freed via ``c_ap_allocator_protocol_free()``. Ref-counted for shared
   use — acquire/release owner semantics.

2. **Heap allocator**: Created via ``c_heap_allocator_new()``, freed via
   ``c_heap_allocator_free()``. Pages are freed when the allocator is
   destroyed.

3. **SHM allocator**: Created via ``c_shm_allocator_new()``, freed via
   ``c_shm_allocator_free()``. SHM objects persist until explicitly
   unlinked (use ``cleanup_dangling()``).

4. **ByteMap**: Created with ``c_bytemap_new()``, freed with
   ``c_bytemap_free()``. Keys are copied; values are just pointers
   (caller manages value lifetimes).

5. **InternString**: Created with ``c_istr_map_new()``, freed with
   ``c_istr_map_free()``. String data is owned by the map's allocator.

Using from Cython
-----------------

To use the C API in your own Cython extensions:

.. code-block:: cython

   # my_extension.pyx
   from cbase.allocator_protocol.c_allocator_protocol cimport (
       allocator_protocol,
       c_ap_allocator_protocol_new,
       c_ap_allocator_protocol_free,
   )

   cdef allocator_protocol* proto = c_ap_allocator_protocol_new(
       4096, NULL, NULL, 0
   )
   try:
       # ... use proto ...
   finally:
       c_ap_allocator_protocol_free(proto)

Use ``cbase.get_include()`` in your ``setup.py`` to get the include
directories containing the ``.pxd`` files:

.. code-block:: python

   from setuptools import setup, Extension
   from Cython.Build import cythonize
   import cbase

   ext = Extension(
       "my_module",
       sources=["my_module.pyx"],
       include_dirs=cbase.get_include(),
       extra_compile_args=["-O3"],
   )
   setup(ext_modules=cythonize(ext, compiler_directives={'language_level': 3}))

Thread Safety
-------------

- **Allocator protocol**: Thread-safe when ``with_lock`` is enabled
- **Heap allocator**: Thread-safe via ``pthread_mutex_t`` (``with_lock`` param)
- **SHM allocator**: Thread-safe via ``pthread_mutex_t`` (``with_lock`` param)
- **ByteMap**: **NOT** internally synchronized — use external locking
- **InternString**: Thread-safe via ``c_istr_synced`` (uses pool mutex)

Performance Considerations
--------------------------

- **Heap allocation**: O(1) alloc/recycle when free list is non-empty
- **SHM allocation**: O(1) alloc from active page, O(n) on page exhaustion
- **ByteMap**: O(1) expected (xxHash3), O(n) worst-case
- **InternString**: O(1) expected lookups, O(k) interning (k = string length)

.. seealso::

   - :doc:`allocator_protocol` — Python API for the allocator protocol
   - :doc:`bytemap` — Python API for ByteMap
   - :doc:`intern_string` — Python API for string interning
