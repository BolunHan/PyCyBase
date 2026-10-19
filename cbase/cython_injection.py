"""Inject a package's Cython declarations into ``Cython/Includes``.

Cython resolves ``cimport <package>`` through its own ``Includes`` directory.
A package that ships ``.pxd`` files must therefore be visible there before
another extension can cimport it.  This module finds the environment the
package was installed into, verifies that Cython is installed in that same
environment, and maintains a relative symlink::

    <site-packages>/Cython/Includes/<name> -> ../../<package>

``inject_cython_includes`` is reused by ``setup.py`` so a source install
performs the injection automatically, and by other packages (for example
``PyAlgoEngine``) that expose Cython declarations of their own::

    # setup.py
    from cbase.cython_injection import inject_cython_includes

    class BuildExt(build_ext):
        def run(self):
            super().run()
            inject_cython_includes(
                "algo_engine",
                source=Path(__file__).parent / "algo_engine",
                editable=self.inplace,  # True for ``pip install -e .``
            )

Every entry point returns a status string instead of raising when the
environment, Cython or the package is unavailable.  Pass ``strict=True`` to
turn those statuses into :class:`CythonInjectionError`.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import site
import subprocess
import sys
import sysconfig
from pathlib import Path

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

INJECTED = "injected"
ALREADY_INJECTED = "already-injected"
UNINJECTED = "uninjected"
NOT_INJECTED = "not-injected"
CONFLICT = "conflict"
FAILED = "failed"
SKIPPED_NO_CYTHON = "skipped-no-cython"
SKIPPED_NO_PACKAGE = "skipped-no-package"
SKIPPED_NO_ENVIRONMENT = "skipped-no-environment"

_SUCCESS = frozenset({INJECTED, ALREADY_INJECTED, UNINJECTED, NOT_INJECTED})

__all__ = [
    "ALREADY_INJECTED",
    "CONFLICT",
    "CythonInjectionError",
    "FAILED",
    "INJECTED",
    "NOT_INJECTED",
    "SKIPPED_NO_CYTHON",
    "SKIPPED_NO_ENVIRONMENT",
    "SKIPPED_NO_PACKAGE",
    "UNINJECTED",
    "cython_injection_path",
    "cython_injection_status",
    "inject_cython_includes",
    "resolve_cython_includes",
    "resolve_site_packages",
    "uninject_cython_includes",
]


class CythonInjectionError(RuntimeError):
    """Raised when injection cannot proceed in strict mode, or for a bad
    explicit source path."""


def _site_packages_candidates(root: Path) -> list[Path]:
    """Return site-packages directories that may belong to *root*.

    ``root`` may be an environment root (POSIX or Windows layout) or an
    explicit site-packages directory.
    """
    if root.name in ("site-packages", "dist-packages"):
        return [root]
    return [
        *sorted(root.glob("lib/python*/site-packages")),
        *sorted(root.glob("lib/python*/dist-packages")),
        root / "Lib" / "site-packages",
        root / "Lib" / "dist-packages",
    ]


def _dedupe(paths: list[Path]) -> list[Path]:
    """Drop duplicate paths while preserving order."""
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = os.path.abspath(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def resolve_site_packages(env: str | os.PathLike[str] | None = None) -> Path | None:
    """Locate the ``site-packages`` directory of the target environment.

    Args:
        env: Virtual-environment root, an explicit ``site-packages`` /
            ``dist-packages`` directory, or ``None`` to inspect the running
            interpreter first, then ``VIRTUAL_ENV`` and ``CONDA_PREFIX``.

    Returns:
        The first existing site-packages directory of the first environment
        that exists.  Within an environment, a directory containing
        ``Cython/Includes`` is preferred, so the returned path is the one
        Cython itself would use.  ``None`` if no candidate exists.

    Note:
        The running interpreter comes first because pip executes ``setup.py``
        with the environment it installs into.  A stale or misconfigured
        ``VIRTUAL_ENV`` (for example one pointing at a pyenv root) must not
        redirect the link to the wrong environment.
    """
    groups: list[list[Path]] = []
    if env is not None:
        groups.append(_site_packages_candidates(Path(env)))
    else:
        interpreter: list[Path] = []
        paths = sysconfig.get_paths()
        for key in ("purelib", "platlib"):
            value = paths.get(key)
            if value:
                interpreter.append(Path(value))
        if site.ENABLE_USER_SITE:
            user_site = site.getusersitepackages()
            if user_site:
                interpreter.append(Path(user_site))
        groups.append(interpreter)

        for variable in ("VIRTUAL_ENV", "CONDA_PREFIX"):
            value = os.environ.get(variable)
            if value:
                groups.append(_site_packages_candidates(Path(value)))

    for group in groups:
        existing = [path for path in _dedupe(group) if path.is_dir()]
        if not existing:
            continue
        for path in existing:
            if (path / "Cython" / "Includes").is_dir():
                return path.resolve()
        return existing[0].resolve()
    return None


def resolve_cython_includes(site_packages: str | os.PathLike[str]) -> Path | None:
    """Return ``<site-packages>/Cython/Includes`` if Cython is installed there."""
    includes = Path(site_packages) / "Cython" / "Includes"
    return includes.resolve() if includes.is_dir() else None


def _resolve_includes(
        env: str | os.PathLike[str] | None,
        site_packages: str | os.PathLike[str] | None,
        includes_dir: str | os.PathLike[str] | None = None,
) -> tuple[Path | None, Path | None, str | None]:
    """Resolve the target site-packages and Cython Includes directories."""
    if sum(value is not None for value in (env, site_packages, includes_dir)) > 1:
        raise ValueError("pass only one of env, site_packages or includes_dir")
    if includes_dir is not None:
        includes = Path(includes_dir)
        if not includes.is_dir():
            return None, None, SKIPPED_NO_CYTHON
        return includes.parent.parent, includes.resolve(), None
    resolved = resolve_site_packages(site_packages if site_packages is not None else env)
    if resolved is None:
        return None, None, SKIPPED_NO_ENVIRONMENT
    includes = resolve_cython_includes(resolved)
    if includes is None:
        return resolved, None, SKIPPED_NO_CYTHON
    return resolved, includes, None


def _resolve_source(package: str, source: str | os.PathLike[str] | None) -> Path | None:
    """Return the package source directory, explicitly or through importlib."""
    if source is not None:
        path = Path(source)
        if not path.is_dir():
            raise CythonInjectionError(f"package source directory does not exist: {path}")
        return path
    try:
        spec = importlib.util.find_spec(package)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations)))
    if spec.origin:
        return Path(spec.origin).parent
    return None


def _link_name(package: str, name: str | None) -> str:
    """Return the name of the entry under ``Cython/Includes``."""
    return name or package.rsplit(".", 1)[-1]


def _is_windows() -> bool:
    """Return whether the running platform is Windows."""
    return os.name == "nt"


def _report(status: str, message: str, strict: bool = False) -> str:
    """Log *message* and return *status*, or raise in strict mode."""
    if strict and status not in _SUCCESS:
        raise CythonInjectionError(f"{status}: {message}")
    if status in _SUCCESS:
        LOGGER.debug("%s: %s", status, message)
    else:
        LOGGER.warning("%s: %s", status, message)
    return status


def _create_link(link_path: Path, target: Path, *, force: bool, strict: bool) -> str:
    """Create a relative symlink at *link_path* pointing to *target*."""
    # Resolve both sides: ``..`` is applied by the kernel after following
    # symlinks, so a relative link computed from logical paths escapes to the
    # wrong directory when the environment root (for example a venv) is a
    # symlink.  ``resolve()`` also handles a target that does not exist yet.
    target_abs = target.resolve()
    relative = os.path.relpath(target_abs, start=link_path.parent.resolve())

    if link_path.is_symlink():
        current = os.readlink(link_path)
        if current == relative or (link_path.parent / current).resolve() == target_abs:
            return _report(ALREADY_INJECTED, f"{link_path} already points to {target_abs}")
        try:
            link_path.unlink()
        except OSError as exc:
            return _report(FAILED, f"could not replace {link_path}: {exc}", strict)
    elif link_path.exists():
        if not force:
            return _report(CONFLICT, f"{link_path} already exists; pass force=True to replace it", strict)
        try:
            if link_path.is_dir():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        except OSError as exc:
            return _report(FAILED, f"could not replace {link_path}: {exc}", strict)

    try:
        os.symlink(relative, link_path, target_is_directory=True)
    except OSError as exc:
        if not _is_windows():
            return _report(FAILED, f"could not create {link_path} -> {relative}: {exc}", strict)
        # Windows without symlink privilege: a junction needs no elevation.
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link_path), str(target_abs)],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as junction_exc:
            return _report(FAILED, f"could not create {link_path} -> {target_abs}: {junction_exc}", strict)

    LOGGER.info("cython include link: %s -> %s", link_path, relative)
    return INJECTED


def inject_cython_includes(
        package: str = "cbase",
        *,
        source: str | os.PathLike[str] | None = None,
        env: str | os.PathLike[str] | None = None,
        site_packages: str | os.PathLike[str] | None = None,
        includes_dir: str | os.PathLike[str] | None = None,
        editable: bool | None = None,
        name: str | None = None,
        force: bool = False,
        strict: bool = False,
) -> str:
    """Create the ``Cython/Includes`` symlink for *package*.

    Args:
        package: Top-level import name of the package, e.g. ``"cbase"`` or
            ``"algo_engine"``.
        source: Path to the package source directory.  Required for editable
            installs; discovered through ``importlib`` when omitted.  When
            given for a non-editable install it also permits linking a
            site-packages copy that the running install has not created yet.
        env: Target environment root.
        site_packages: Explicit target site-packages directory.  Mutually
            exclusive with *env*.  When neither is given, the running
            interpreter is inspected first, then ``VIRTUAL_ENV`` /
            ``CONDA_PREFIX``.
        includes_dir: Explicit ``Cython/Includes`` directory.  Mutually
            exclusive with *env* and *site_packages*; useful for tests and
            layouts that do not follow the standard environment shape.
        editable: ``True`` links to *source* (in-place install), ``False``
            links to the installed ``site-packages/<package>`` copy.  ``None``
            checks ``setup.py develop`` / ``editable`` arguments and otherwise
            uses the installed copy when present, falling back to *source*.
        name: Link name under ``Cython/Includes``.  Defaults to the last
            component of *package*.
        force: Replace a real file or directory at the link path.  Existing
            symlinks are always replaced when they point elsewhere.
        strict: Raise :class:`CythonInjectionError` instead of returning a
            skip or conflict status.

    Returns:
        One of ``injected``, ``already-injected``, ``conflict``, ``failed``,
        ``skipped-no-environment``, ``skipped-no-cython`` or
        ``skipped-no-package``.
    """
    resolved, includes, skip = _resolve_includes(env, site_packages, includes_dir)
    if resolved is None:
        return _report(
            SKIPPED_NO_ENVIRONMENT,
            f"no site-packages directory found for environment {env!r}",
            strict,
        )
    if includes is None:
        return _report(SKIPPED_NO_CYTHON, f"Cython is not installed in {resolved}", strict)

    installed = resolved.joinpath(*package.split("."))
    source_dir = None if editable is False else _resolve_source(package, source)

    if editable is None:
        editable = any(arg in {"develop", "editable"} for arg in sys.argv[1:])
        if not editable and not installed.is_dir() and source_dir is not None:
            editable = True

    if editable:
        if source_dir is None:
            return _report(
                SKIPPED_NO_PACKAGE,
                f"editable injection of {package!r} needs a source directory",
                strict,
            )
        target = source_dir
    else:
        target = installed
        # setup.py passes source even for wheel builds, because the target
        # copy appears only after the build finishes.  A standalone call has
        # no such context, so it must point at something that exists.
        if source is None and not installed.is_dir():
            return _report(
                SKIPPED_NO_PACKAGE,
                f"{package!r} is not installed in {resolved} and no source was given",
                strict,
            )

    link_path = includes / _link_name(package, name)
    return _create_link(link_path, target, force=force, strict=strict)


def uninject_cython_includes(
        package: str = "cbase",
        *,
        env: str | os.PathLike[str] | None = None,
        site_packages: str | os.PathLike[str] | None = None,
        includes_dir: str | os.PathLike[str] | None = None,
        name: str | None = None,
        strict: bool = False,
) -> str:
    """Remove the ``Cython/Includes`` symlink for *package*.

    Only symlinks are removed; a real file or directory at the link path is
    reported as ``conflict`` and left untouched.

    Returns:
        One of ``uninjected``, ``not-injected``, ``conflict``, ``failed`` or
        a ``skipped-*`` status.
    """
    _, includes, skip = _resolve_includes(env, site_packages, includes_dir)
    if skip is not None:
        return _report(skip, f"cannot uninject {package!r}: {skip}", strict)

    link_path = includes / _link_name(package, name)
    if link_path.is_symlink():
        try:
            link_path.unlink()
        except OSError as exc:
            return _report(FAILED, f"could not remove {link_path}: {exc}", strict)
        return _report(UNINJECTED, f"removed {link_path}")
    if link_path.exists():
        return _report(CONFLICT, f"{link_path} is not a symlink; leaving it untouched", strict)
    return NOT_INJECTED


def cython_injection_status(
        package: str = "cbase",
        *,
        env: str | os.PathLike[str] | None = None,
        site_packages: str | os.PathLike[str] | None = None,
        includes_dir: str | os.PathLike[str] | None = None,
        name: str | None = None,
) -> str:
    """Report the state of the ``Cython/Includes`` entry for *package*.

    Returns:
        ``injected`` when the entry is a symlink (including a link whose
        target will be installed later), ``not-injected`` when it is absent,
        ``conflict`` when a real file or directory occupies the path, or a
        ``skipped-*`` status when the environment cannot be inspected.
    """
    _, includes, skip = _resolve_includes(env, site_packages, includes_dir)
    if skip is not None:
        return skip

    link_path = includes / _link_name(package, name)
    if link_path.is_symlink():
        return INJECTED
    if link_path.exists():
        return CONFLICT
    return NOT_INJECTED


def cython_injection_path(
        package: str = "cbase",
        *,
        env: str | os.PathLike[str] | None = None,
        site_packages: str | os.PathLike[str] | None = None,
        includes_dir: str | os.PathLike[str] | None = None,
        name: str | None = None,
) -> Path | None:
    """Return the path of the ``Cython/Includes`` entry, or ``None``."""
    _, includes, _ = _resolve_includes(env, site_packages, includes_dir)
    if includes is None:
        return None
    return includes / _link_name(package, name)
