PyCyBase Documentation
======================

Common C / Cython dual interfaces for Python HFT projects.

**PyCyBase** provides low-level allocator infrastructure shared across
HFT (High-Frequency Trading) projects. It features a family of Cython
extension modules that expose fast memory allocators, hash maps, and
string interning — all built on a pluggable allocator protocol with
heap, shared-memory, and raw-``malloc`` backends.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   allocator_protocol
   heap_allocator
   shm_allocator
   bytemap
   intern_string
   backports
   env_config
   c_api
   api_reference

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
