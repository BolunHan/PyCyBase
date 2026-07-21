Installation
============

PyCyBase is a **Cython extension package** — it cannot be used with
``pip install -e .`` (editable mode breaks ``.pxd`` resolution for
downstream Cython projects that ``cimport`` from it).  Extensions must
be compiled in-place before installation.

Quick Build (POSIX)
-------------------

.. code-block:: bash

   git clone https://github.com/BolunHan/PyCyBase.git
   cd PyCyBase

   # Build + install (recommended)
   ./build.sh -i

   # Or via Makefile:
   make build && pip install -U . --no-build-isolation

   # Or step by step:
   python setup.py build_ext --inplace --verbose --force
   pip install -U . --no-build-isolation

Build Script Reference
----------------------

``build.sh``
~~~~~~~~~~~~

The primary build script for POSIX (Linux/macOS).  Supports venv
activation, clean/rebuild/all-clean modes, optional pip install, and
compile-time macro introspection.

.. code-block:: bash

   ./build.sh [options]

Options:

========  ============================================================
``-v``    Path to virtual environment to activate before building
``-i``    ``pip install .`` after build
``-r``    Force-reinstall (uninstall + ``pip install --force-reinstall``)
``-c``    Clean build artifacts only (no build)
``-a``    Deep clean — remove ``.c`` and ``.so`` files, then exit
``-l``    List all compile-time macros and their default values
``-h``    Show help
========  ============================================================

``Makefile``
~~~~~~~~~~~~

Convenience targets wrapping ``build.sh``:

=============  =====================================================
Target         Effect
=============  =====================================================
``build``      Clean + ``build_ext --inplace --verbose --force``
``dev``        Alias for ``build``
``install``    Build + ``pip install .``
``reinstall``  Build + force-reinstall (uninstall first)
``clean``      Remove ``build/``, ``*.egg-info``, ``includes/``
``clean-all``  ``clean`` + delete all ``.c`` and ``.so`` files
``list-args``  List compile-time macros (delegates to ``build.sh -l``)
=============  =====================================================

``build.ps1`` (Windows)
~~~~~~~~~~~~~~~~~~~~~~~

PowerShell build script for Windows NT.  Activates a specified venv,
cleans artifacts, and runs ``build_ext --inplace --verbose --force``.

.. code-block:: powershell

   .\build.ps1 -VenvPath "C:\Users\...\venv_313"

``nt_build.py`` (Cross-Compile from Linux)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Paramiko-based orchestrator that syncs the local source tree to a
Windows VM via SSH, then triggers ``build.ps1`` and runs tests.
Configured via ``nt_config.json``.

.. code-block:: bash

   python nt_build.py                # sync → build → test
   python nt_build.py --host Win11-CN

Compile-Time Macros
-------------------

PyCyBase exposes numerous ``#define`` macros that control allocation
behaviour, page sizes, thread safety, and debugging.  Override any
macro at compile time by setting an environment variable of the same
name:

.. code-block:: bash

   DEBUG=1 ./build.sh            # Enable debug mode
   AP_ALLOC_VIGILANT=0 make build # Disable vigilant/canary checks

**Listing available macros:**

.. code-block:: bash

   ./build.sh -l        # Reads macros.json; auto-generates via probe.py if missing
   make list-args        # Same, via Makefile
   python probe.py       # Run the probe manually

``probe.py`` scans Cython ``.pxd`` files for ``cdef extern from``
headers, extracts every ``#define`` macro from those headers, and
writes a JSON inventory to ``macros.json``.

**Key macros** (see ``macros.json`` for the full list):

======================================== ===================== ==========================================
Macro                                    Default               Description
======================================== ===================== ==========================================
``AP_ALLOC_VIGILANT``                    ``1``                 Enable bounds/canary validation
``AP_ALLOC_MAGIC``                       ``0xCFBBBBFCULL``     Magic sentinel for live allocations
``AP_DEALLOC_MAGIC``                     ``0xDEADDEADULL``     Magic sentinel for freed memory
``AP_DECREF_AUTOFREE``                   ``1``                 Auto-free on refcount reaching zero
``AP_ALLOC_WITH_LOCK``                   ``1``                 Enable pthread mutex locking
``AP_ALLOC_WITH_SHM``                    ``0``                 Default to SHM (off = heap default)
``AP_ALLOC_WITH_FREELIST``               ``1``                 Enable free-list reuse
``AP_HEAP_AUTOPAGE_CAPACITY``            ``64 KiB``            Default heap page size
``AP_HEAP_AUTOPAGE_CAPACITY_MAX``        ``16 MiB``            Max heap page size
``AP_HEAP_AUTOPAGE_ALIGNMENT``           ``4 KiB``             Heap page alignment
``AP_SHM_AUTOPAGE_CAPACITY``             ``64 KiB``            Default SHM page size
``AP_SHM_AUTOPAGE_CAPACITY_MAX``         ``16 MiB``            Max SHM page size
``AP_SHM_AUTOPAGE_ALIGNMENT``            ``4 KiB``             SHM page alignment
``AP_SHM_ALLOCATOR_PREFIX``              ``/c_cbase_shm``      SHM name prefix
``AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE`` ``128 GiB``           Virtual region size
``AP_SHM_NAME_LEN``                      ``256``               Max SHM name length
``AP_SHM_PREFIX_MAX``                    ``64``                Max custom prefix length
======================================== ===================== ==========================================

Prerequisites
-------------

- **Python**: 3.12 or later
- **Build**: Cython ≥ 3.0, C11 compiler (GCC/Clang on Linux, MSVC on Windows)
- **Runtime**: No external Python dependencies (stdlib only for the Python layer)
- **Docs** (optional): ``sphinx`` + ``furo``

Linux
~~~~~

.. code-block:: bash

   # Ubuntu/Debian
   sudo apt-get install build-essential python3-dev

   # Arch/Manjaro
   sudo pacman -S base-devel

Windows
~~~~~~~

- Visual C++ Build Tools (`download <https://visualstudio.microsoft.com/visual-cpp-build-tools/>`_)
- Select "Desktop development with C++" and Windows SDK during install

Verifying the Build
-------------------

.. code-block:: python

   import cbase
   print(cbase.__version__)

   from cbase.allocator_protocol import AllocatorProtocol, AP_SHARED
   from cbase.bytemap import ByteMap
   from cbase.intern_string import POOL

Using ``get_include()`` in Downstream Projects
----------------------------------------------

PyCyBase provides ``cbase.get_include()`` to help downstream Cython
extensions find ``.pxd`` and ``.h`` files:

.. code-block:: python

   from setuptools import setup, Extension
   from Cython.Build import cythonize
   import cbase

   ext = Extension(
       "my_module",
       sources=["my_module.pyx"],
       include_dirs=cbase.get_include(),
   )
   setup(ext_modules=cythonize([ext]))

.. important::
   ``pip install -e .`` is **not** supported for PyCyBase.  Editable
   installs break ``.pxd`` resolution because ``cimport`` searches
   ``Cython/Includes/`` for the package name, not the editable
   egg-link.  Always use ``setup.py build_ext --inplace`` followed by
   ``pip install -U . --no-build-isolation``.

Platform-Specific Notes
-----------------------

SHM Allocator
~~~~~~~~~~~~~

- **POSIX** (Linux/macOS): Full ``SharedMemoryAllocator`` with
  ``shm_open``/``mmap``, cross-process pointer stability.
- **Windows**: ``NtSharedMemoryAllocator`` compat layer (limited
  functionality, no cross-process sharing).

NB: the top-level ``cbase.allocator_protocol`` package selects the
correct backend automatically based on ``sys.platform``.

NT Cross-Compilation
~~~~~~~~~~~~~~~~~~~~

For cross-compiling to Windows from a Linux host, use the NT build
orchestrator:

.. code-block:: bash

   pip install paramiko              # (in the host venv)
   python nt_build.py                # sync → build → test on remote VM

Configuration is in ``nt_config.json``.  See the memory files for
detailed VM connection and environment setup.

Troubleshooting
---------------

**Compilation fails with missing Python.h**

.. code-block:: bash

   sudo apt-get install python3-dev

**Cython version mismatch**

.. code-block:: bash

   pip install -U cython

**Binary incompatibility after rebuild**

If you see ``ValueError: ... size changed, may indicate binary
incompatibility``, do a deep clean and rebuild:

.. code-block:: bash

   ./build.sh -a            # Remove all .c and .so files
   ./build.sh -i            # Rebuild and install

**Multiprocessing forkserver errors** (Python 3.14 on Arch)

Set the multiprocessing start method before building:

.. code-block:: bash

   export N_THREADS=0
   python setup.py build_ext --inplace --verbose --force

Building Documentation
----------------------

.. code-block:: bash

   pip install sphinx furo
   cd docs
   sphinx-build -M html . _build

Open ``docs/_build/html/index.html`` in a browser.
