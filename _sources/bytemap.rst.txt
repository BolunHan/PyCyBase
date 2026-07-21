ByteMap
=======

Module: ``cbase.bytemap``

A family of fast, C-backed hash maps for byte-string keys with several
variants: basic ``ByteMap``, extended ``ByteMapEx``, and bound
convenience wrappers.

.. automodule:: cbase.bytemap.c_bytemap
   :members:
   :undoc-members:
   :show-inheritance:

Map Variants
------------

ByteMap
~~~~~~~

The simplest variant — maps ``bytes`` keys to ``bytes`` values. Stores
references to ``PyObject*`` keys and values.

.. code-block:: python

   from cbase.bytemap import ByteMap

   bm = ByteMap()
   bm[b"key"] = b"value"
   assert bm[b"key"] == b"value"
   assert b"key" in bm
   del bm[b"key"]

ByteMapEx
~~~~~~~~~

Extended variant — maps arbitrary ``PyObject*`` keys to ``PyObject*``
values with callback support, cloning, and fine-grained control.

Callback registration:

.. code-block:: python

   from cbase.bytemap import ByteMapEx

   def on_set(event, entry, ctx):
       print(f"Set: {event}, key={entry.key}")

   bm = ByteMapEx()
   bm.register_callback(on_set)
   bm["key"] = "value"  # Fires callback

ByteMapExDouble
~~~~~~~~~~~~~~~

Variant that maps ``bytes`` keys to C ``double`` values (not Python
``float`` objects), avoiding boxing overhead.

Bound Wrappers
~~~~~~~~~~~~~~

Bound map variants lock the key to a specific ``bytes`` object for
convenience and performance:

.. code-block:: python

   from cbase.bytemap import BoundByteMap, BoundByteMapEx, BoundByteMapExDouble, BoundByteSet

   # BoundByteMap — fixed key, variable bytes value
   bbm = BoundByteMap(b"my_key")
   bbm.set(b"my_value")
   val = bbm.get()

   # BoundByteSet — membership-only, no value storage
   bbs = BoundByteSet(b"my_key")
   bbs.add()  # Mark as present
   assert bbs.contains()

Usage Examples
--------------

Rehashing to reduce collisions:

.. code-block:: python

   bm = ByteMap()
   for i in range(10000):
       bm[f"key_{i}".encode()] = f"val_{i}".encode()
   bm.rehash()  # Rebalance with larger capacity if needed

Compile-Time Constants
----------------------

.. code-block:: python

   from cbase.bytemap.c_bytemap import (
       MIN_BYTEMAP_CAPACITY,       # Minimum hash table capacity
       DEFAULT_BYTEMAP_CAPACITY,   # Default initial capacity
       BYTEMAP_GROWTH_FACTOR,      # Growth multiplier on rehash
       MAX_BYTEMAP_CAPACITY,       # Maximum capacity ceiling
   )

Hashing
-------

The ByteMap uses **xxHash3** (64-bit) for key hashing. The ``xxhash.h``
and ``xxhash.c`` files in ``cbase/bytemap/`` provide a vendored copy of
the xxHash library.

Thread Safety
-------------

ByteMap operations are **not** internally synchronized. Use external
locking or the ``with_lock`` parameter of the allocator protocol when
accessing maps from multiple threads.

.. seealso::

   - :doc:`allocator_protocol` — The memory backing for ByteMap entries
   - :doc:`intern_string` — String interning built on the allocator protocol
