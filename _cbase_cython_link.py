"""Create ``Cython/Includes/cbase`` in the environment this package is installed in.

A wheel runs no code at installation time, so the wheel ships
``_cbase_cython_link.pth``; ``site`` imports this module at interpreter
startup and it maintains the same relative symlink a source build creates::

    <site-packages>/Cython/Includes/cbase -> ../../cbase

The hook is a no-op when Cython is not installed in the environment, when the
link already resolves, or when a real entry occupies the link path.  The link
logic lives in ``cbase/cython_injection.py``, loaded by path so importing this
module never executes ``cbase/__init__``.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

PACKAGE = "cbase"
INJECTION_MODULE = "cython_injection.py"


def _load_injection(source: Path):
    """Load ``cbase/cython_injection.py`` from *source* without importing cbase."""
    module_path = source / INJECTION_MODULE
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_cbase_cython_injection", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_source(site_packages: Path) -> Path | None:
    """Return the installed or editable source directory of the package."""
    installed = site_packages / PACKAGE
    if installed.is_dir():
        return installed
    try:
        spec = importlib.util.find_spec(PACKAGE)
    except (ImportError, ValueError):
        return None
    locations = getattr(spec, "submodule_search_locations", None)
    if not locations:
        return None
    return Path(next(iter(locations)))


def ensure_cython_include(site_packages: str | os.PathLike[str] | None = None) -> str | None:
    """Create the ``Cython/Includes`` link if this environment needs it.

    Args:
        site_packages: Directory holding the installed package.  Defaults to
            the directory containing this module.

    Returns:
        The injection status, or ``None`` when no link was attempted.
    """
    root = Path(site_packages) if site_packages is not None else Path(__file__).resolve().parent
    includes = root / "Cython" / "Includes"
    if not includes.is_dir():
        return None

    link = includes / PACKAGE
    if link.is_symlink():
        if link.exists():
            return "already-injected"
        try:
            link.unlink()
        except OSError:
            return None
    elif link.exists():
        return "conflict"

    source = _resolve_source(root)
    if source is None:
        return None
    module = _load_injection(source)
    if module is None:
        return None
    try:
        return module.inject_cython_includes(
            PACKAGE,
            source=source,
            editable=True,
            site_packages=root,
        )
    except Exception:
        return None


try:
    ensure_cython_include()
except Exception:
    pass
