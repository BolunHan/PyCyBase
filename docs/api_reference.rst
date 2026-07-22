API Reference
=============

This page provides auto-generated API documentation from docstrings and
type stubs for modules without dedicated guide pages. For detailed
usage, see the module-specific pages.

.. note::
   For usage examples and conceptual guides, see:

   - :doc:`allocator_protocol` — Allocator protocol and config contexts
   - :doc:`heap_allocator` — In-process heap allocator
   - :doc:`shm_allocator` — Shared-memory page allocator
   - :doc:`bytemap` — Fast hash maps
   - :doc:`intern_string` — String interning
   - :doc:`env_config` — EnvConfigContext base class
   - :doc:`backports` — Python C API backports (128-bit int, dict)
   - :doc:`c_api` — C-level API for extension developers

Backports
---------

.. automodule:: cbase.backports
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: cbase.backports.pylong
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

.. automodule:: cbase.backports.pydict
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Top-Level Package
-----------------

.. automodule:: cbase
   :members:
   :undoc-members:
   :show-inheritance:

Environment Config
------------------

.. automodule:: cbase.env
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Type Stubs
----------

The package includes complete type stubs (``.pyi`` files) for all Cython
modules:

- ``cbase/env.pyi``
- ``cbase/allocator_protocol/c_allocator_protocol.pyi``
- ``cbase/allocator_protocol/c_heap_allocator.pyi``
- ``cbase/allocator_protocol/c_shm_allocator.pyi``
- ``cbase/intern_string/c_intern_string.pyi``

These provide full type information for IDEs and type checkers like
mypy or pyright.
