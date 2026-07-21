Environment Config Context
===========================

Module: ``cbase.env``

A Cython-backed context manager for temporary environment configuration
changes. Used as the base class for :doc:`AllocatorConfigContext
<allocator_protocol>`.

.. automodule:: cbase.env
   :members:
   :undoc-members:
   :show-inheritance:

Usage
-----

``EnvConfigContext`` tracks configuration overrides and restores originals
on exit. It supports three usage patterns:

**Context manager:**

.. code-block:: python

   from cbase.env import EnvConfigContext

   ctx = EnvConfigContext(debug=True, log_level=3)
   with ctx:
       # debug=True, log_level=3 are active
       ...
   # Original values restored

**Decorator:**

.. code-block:: python

   @EnvConfigContext(cache_size=1024)
   def my_function():
       # cache_size=1024 active during this call
       ...

**Composition with ``|`` (union) and ``~`` (invert):**

.. code-block:: python

   a = EnvConfigContext(debug=True)
   b = EnvConfigContext(log_level=5)

   merged = a | b          # Both debug=True and log_level=5
   inverted = ~a           # debug=False

Inheritance
-----------

``AllocatorConfigContext`` (in ``cbase.allocator_protocol``) extends
``EnvConfigContext`` to additionally propagate configuration changes to
the heap and SHM allocator backends. See :doc:`allocator_protocol`.

.. code-block:: python

   from cbase.allocator_protocol import AllocatorConfigContext

   ctx = AllocatorConfigContext(locked=True, autopage_capacity=65536)
   with ctx:
       # Thread-safety enabled, 64 KiB auto pages
       ...

.. seealso::

   - :doc:`allocator_protocol` — ``AllocatorConfigContext`` subclass
