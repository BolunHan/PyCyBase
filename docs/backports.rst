Backports
=========

Package: ``cbase.backports``

C API backports that provide a uniform interface across Python versions.
When the target Python provides the native API, the shim is a thin
``#define`` alias; otherwise a ``static inline`` fallback is compiled.

pylong — 128-bit Integer Backport
----------------------------------

Module: ``cbase.backports.pylong``

Bridges Python ``int`` ↔ 128-bit native integer types (``uint128_t`` /
``int128_t``).  The native types cannot be represented directly in
Cython (GCC ``__int128_t`` has no ``pxd`` representation), so the
Python-level API works with 16-byte little-endian ``bytes`` buffers.

On GCC/Clang, ``uint128_t`` / ``int128_t`` map to ``__uint128_t`` /
``__int128_t``.  On MSVC (which lacks 128-bit integers), they are
emulated as two-limb little-endian structs — byte-compatible with the
GCC layout, so 16-byte buffers round-trip identically across compilers.

.. automodule:: cbase.backports.pylong
   :members:
   :undoc-members:
   :show-inheritance:

Usage
~~~~~

.. code-block:: python

   from cbase.backports.pylong import (
       pylong_from_uint128,
       pylong_as_uint128,
   )

   # bytes → Python int
   val = pylong_from_uint128(b'\xff' * 16)
   print(val)  # 340282366920938463463374607431768211455

   # Python int → bytes (16-byte little-endian)
   buf = pylong_as_uint128(42)
   print(buf.hex())  # 2a0000000000000000000000000000

   # Range constants
   from cbase.backports.pylong import _UINT128_MAX, _INT128_MIN
   print(_UINT128_MAX)  # 2**128 - 1
   print(_INT128_MIN)   # -2**127

C-Level Interface
~~~~~~~~~~~~~~~~~

The header ``cbase/backports/pylong.h`` exposes these C functions
(declared in ``cbase.backports.pylong.pxd`` for ``cimport``):

.. code-block:: cython

   from cbase.backports.pylong cimport (
       uint128_t, int128_t,
       c_read_uint128, c_write_uint128,
       PyLong_FromUInt128, PyLong_AsUInt128,
       c_u128_cmp,
   )

=======================  ====================================================
Function                 Description
=======================  ====================================================
``c_read_uint128(p)``    Read ``uint128_t`` from a byte buffer
``c_write_uint128(p, v)`` Write ``uint128_t`` to a byte buffer
``c_read_int128(p)``     Read ``int128_t`` from a byte buffer
``c_write_int128(p, v)`` Write ``int128_t`` to a byte buffer
``PyLong_FromUInt128(v)``  Convert ``uint128_t`` → Python ``int``
``PyLong_FromInt128(v)``   Convert ``int128_t`` → Python ``int``
``PyLong_AsUInt128(obj, *v)`` Convert Python ``int`` → ``uint128_t``
``PyLong_AsInt128(obj, *v)``  Convert Python ``int`` → ``int128_t``
``c_u128_cmp(a, b)``       Compare two ``uint128_t`` values
``c_i128_cmp(a, b)``       Compare two ``int128_t`` values
=======================  ====================================================

Cross-Platform Design
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   #if defined(__SIZEOF_INT128__)
   typedef __int128_t     int128_t;
   typedef __uint128_t    uint128_t;
   #else
   // MSVC: two-limb little-endian struct
   typedef struct { uint64_t lo; int64_t  hi; } int128_t;
   typedef struct { uint64_t lo; uint64_t hi; } uint128_t;
   #endif

Because the Cython boundary always converts via ``bytes`` (16-byte
little-endian), the internal representation is opaque to Python code.
This means 16-byte buffers produced on Linux (GCC ``__int128_t``) can
be consumed on Windows (MSVC struct) and vice versa.

pydict — Dict C API Backport
-----------------------------

Module: ``cbase.backports.pydict``

Backports ``PyDict_Pop`` (added in Python 3.13) for older Python
versions.

.. automodule:: cbase.backports.pydict
   :members:
   :undoc-members:
   :show-inheritance:

C-Level Interface
~~~~~~~~~~~~~~~~~

.. code-block:: cython

   from cbase.backports.pydict cimport BP_PyDict_Pop

.. code-block:: c

   int BP_PyDict_Pop(PyObject *op, PyObject *key, PyObject **result);

Returns 0 on success (key removed, ``*result`` is a new strong
reference), 1 if the key is not present (``*result`` is NULL), or -1
on error (exception set).

When ``PY_VERSION_HEX >= 0x030D0000``, ``BP_PyDict_Pop`` is a
``#define`` alias for the native ``PyDict_Pop``.  On earlier versions,
a ``static inline`` shim uses ``PyDict_GetItemWithError`` +
``PyDict_DelItem``.

.. seealso::

   - :doc:`c_api` — C API reference for PyCyBase's other headers
   - :doc:`installation` — Cross-platform build and NT compilation notes
