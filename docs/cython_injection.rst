Cython Include Injection
========================

Cython resolves ``cimport <package>`` through its own ``Includes`` directory.
A package that ships ``.pxd`` files must therefore appear under
``<site-packages>/Cython/Includes`` before another extension can cimport it.
``cbase.cython_injection`` finds the target environment, verifies that Cython
is installed there, and maintains a relative symlink:

.. code-block:: text

   <site-packages>/Cython/Includes/<package> -> ../../<package>

The module is standard-library only and is reused by the PyCyBase ``setup.py``
so source installs inject automatically.  Other packages can call the same
entry points, for example ``PyAlgoEngine`` (import name ``algo_engine``).

Public API
----------

.. autofunction:: cbase.cython_injection.inject_cython_includes

.. autofunction:: cbase.cython_injection.uninject_cython_includes

.. autofunction:: cbase.cython_injection.cython_injection_status

.. autofunction:: cbase.cython_injection.cython_injection_path

.. autofunction:: cbase.cython_injection.resolve_site_packages

.. autofunction:: cbase.cython_injection.resolve_cython_includes

.. autoclass:: cbase.cython_injection.CythonInjectionError

Environment detection
---------------------

The target site-packages directory is selected in this order:

1. an explicit ``site_packages=`` directory;
2. an explicit ``env=`` environment root (POSIX ``lib/python*/site-packages``
   or Windows ``Lib/site-packages``);
3. the running interpreter's ``sysconfig`` paths;
4. ``VIRTUAL_ENV`` and ``CONDA_PREFIX``.

The running interpreter is checked before the environment variables because
pip runs ``setup.py`` with the interpreter it installs into.  A stale
``VIRTUAL_ENV`` (for example one pointing at a pyenv root) therefore cannot
redirect the link to the wrong environment.  Symlinked environment roots are
resolved before the relative link is computed, so ``..`` traversal stays
inside the physical directory tree.

Injection modes
---------------

``editable=False``
   Link ``site-packages/<package>``.  During a wheel build the installed copy
   may not exist yet; ``setup.py`` passes ``source=`` to permit the link to be
   created ahead of installation.

``editable=True``
   Link the package source directory.  This is what ``pip install -e .``
   needs, and it keeps the ``.pxd`` files current while editing.

``editable=None``
   Detect ``setup.py develop`` / ``editable`` arguments, then prefer an
   existing installed copy and fall back to ``source=``.

Status values
-------------

Every entry point returns a plain status string:

============================  ============================================================
``injected``                  A new relative symlink was created (or a stale
                              symlink was repointed).
``already-injected``          The link already points at the requested target.
``uninjected``                A symlink was removed.
``not-injected``              No symlink exists at the link path.
``conflict``                  A real file or directory occupies the link path;
                              it is left untouched unless ``force=True``.
``failed``                    The link could not be created or removed.
``skipped-no-environment``    No site-packages directory was found.
``skipped-no-cython``         Cython is not installed in the target environment.
``skipped-no-package``        The package (or its source directory) was not
                              found.
============================  ============================================================

Pass ``strict=True`` to raise ``CythonInjectionError`` instead of returning a
skip, conflict or failure status.

Idempotency and removal
-----------------------

Calling ``inject_cython_includes`` twice is safe: the second call reports
``already-injected``.  ``uninject_cython_includes`` removes only symlinks;
a real directory at the link path reports ``conflict`` and is preserved.

Windows
-------

``os.symlink`` may require Developer Mode or elevated privileges.  When it
fails on Windows the injector falls back to a directory junction
(``mklink /J``), which needs no elevation.  If neither works the call reports
``failed`` and the build continues.

Reusing from PyAlgoEngine
-------------------------

Add the call to the downstream ``setup.py`` after the extensions are built.
``build_ext.inplace`` is true for ``pip install -e .`` and false for a wheel
build, which is exactly the distinction the injector needs:

.. code-block:: python

   from pathlib import Path
   from setuptools.command.build_ext import build_ext
   from cbase.cython_injection import inject_cython_includes

   class BuildExt(build_ext):
       def run(self):
           super().run()
           status = inject_cython_includes(
               "algo_engine",
               source=Path(__file__).parent / "algo_engine",
               editable=self.inplace,
           )
           print(f"[build_py] Cython include injection: {status}")

The resulting entry can be verified from Python:

.. code-block:: python

   import os
   from cbase.cython_injection import cython_injection_path

   link = cython_injection_path("algo_engine")
   print(os.readlink(link))   # ../../algo_engine
