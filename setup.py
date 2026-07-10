import os
import platform
import re
import shutil
import sys
from contextlib import suppress
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

# ==============================
# Setup Configuration
# ==============================

PACKAGE_NAME = "cbase"
DISPLAY_NAME = "PyCyBase"

WITH_ANNOTATION = False
COMPILE_FLAGS = ["/Ox"] if platform.system() == "Windows" else ['-O3', '-march=native']
REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
N_CORES = os.cpu_count() or 1
N_THREADS = max(1, N_CORES - 2)
__VERSION__ = match.group(1) if (match := re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', (Path(REPO_ROOT) / PACKAGE_NAME / '__init__.py').read_text(), re.MULTILINE)) else "unknown"

ext_modules = []
c_extensions = []
cython_extension = []


# ==============================
# Custom Build Extension Class
# ==============================


class BuildExtWithConfig(build_ext):
    __cy_modules__ = [
        "cbase",
        "cbase.allocator_protocol",
    ]

    def initialize_options(self):
        super().initialize_options()
        self.parallel = N_THREADS

    def run(self):
        self.pre_compile()

        super().run()

        self.post_compile()
        print(f"[build_py] <{DISPLAY_NAME}> v{__VERSION__} setup complete. Built {len(self.extensions)} Cython extensions.")

    def build_extensions(self):
        macros = []
        for macro in ["DEBUG"]:
            val = os.environ.get(macro)
            if val:
                print(f'[build_py] Compile-time variable {macro} overridden with value {val}')
                macros.append((macro, val))
        for ext in self.extensions:
            ext.define_macros = macros
        super().build_extensions()

    def pre_compile(self):
        self.collect_sources()

    def post_compile(self):
        # Monkey hack the "__init__.pxd" issue:
        self.inject_pxd()

        # Inject the generated includes/ mirror into build_lib so it gets packaged
        self.inject_sources()

    @classmethod
    def collect_sources(cls) -> None:
        project_root = Path(__file__).resolve().parent
        source_root = project_root / PACKAGE_NAME
        include_root = project_root / PACKAGE_NAME / "includes"
        mirror_root = include_root / PACKAGE_NAME

        if mirror_root.exists():
            shutil.rmtree(mirror_root)

        copied = 0
        source_patterns = ["*.h", "*.c", "*.cpp"]
        for pattern in source_patterns:
            for source_file in sorted(source_root.rglob(pattern)):
                # Skip files inside the generated include_root
                if include_root in source_file.parents:
                    continue
                dest = include_root.joinpath(*source_file.relative_to(project_root).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, dest)
                copied += 1

        print(f"[build_py] <{DISPLAY_NAME}> mirrored {copied} C source file(s) -> {include_root.relative_to(project_root)}")

    def inject_sources(self) -> None:
        project_root = Path(__file__).resolve().parent
        include_root = project_root / PACKAGE_NAME / "includes"
        mirror_root = include_root / PACKAGE_NAME

        if not mirror_root.exists():
            return

        dest_root = Path(self.build_lib, PACKAGE_NAME, "includes", PACKAGE_NAME)
        if dest_root.exists():
            shutil.rmtree(dest_root)

        shutil.copytree(mirror_root, dest_root)
        print(f"[build_py] <{DISPLAY_NAME}> injected includes mirror -> {dest_root.relative_to(Path(self.build_lib))}")

    @classmethod
    def remove_pxd(cls) -> None:
        project_root = Path(__file__).resolve().parent

        for module in cls.__cy_modules__:
            src_dir = project_root.joinpath(*module.split("."))
            init_pxd = src_dir / "__init__.pxd"

            if init_pxd.exists():
                print(f"[build_py] [pre_compile] Removing {init_pxd}")
                with suppress(FileNotFoundError):
                    init_pxd.unlink()

        # Temporarily move the cbase symlink/dir from Cython/Includes
        # to prevent cythonize from picking up stale pxd files from an
        # installed version.
        cls._pxd_backup = []
        try:
            import Cython.Includes as _cy_includes
            includes_dir = Path(next(iter(_cy_includes.__path__)))
            pkg_link = includes_dir / PACKAGE_NAME
            if pkg_link.exists():
                backup = pkg_link.with_name(f"{PACKAGE_NAME}.cy_bak")
                print(f"[build_py] [pre_compile] Moving Cython/Includes symlink {pkg_link.name} -> {backup.name}")
                pkg_link.rename(backup)
                cls._pxd_backup.append((backup, pkg_link))
        except Exception as e:
            print(f"[build_py] [pre_compile] Warning: Could not handle Cython/Includes symlink: {e}")

    @classmethod
    def restore_pxd(cls) -> None:
        """Restore symlink in Cython/Includes after cythonize."""
        for backup, original in getattr(cls, '_pxd_backup', []):
            if backup.exists():
                print(f"[build_py] [pre_compile] Restoring Cython/Includes symlink {backup.name} -> {original.name}")
                backup.rename(original)
        cls._pxd_backup = []

    def inject_pxd(self) -> None:
        project_root = Path(__file__).resolve().parent

        for module in self.__cy_modules__:
            src_dir = project_root.joinpath(*module.split("."))
            pkg_dir = Path(self.build_lib, *module.split("."))

            infra_pxd = src_dir / "__infra__.pxd"
            if not infra_pxd.exists():
                continue

            # Inject into build_lib (for wheel / deploy)
            pkg_dir.mkdir(parents=True, exist_ok=True)
            init_pxd = pkg_dir / "__init__.pxd"
            print(f"[build_py] [post_compile] Injecting {infra_pxd} -> {init_pxd}")
            shutil.copyfile(infra_pxd, init_pxd)

            # Also restore into src_dir (so source tree keeps __init__.pxd)
            src_init_pxd = src_dir / "__init__.pxd"
            if not src_init_pxd.exists():
                print(f"[build_py] [post_compile] Restoring {infra_pxd} -> {src_init_pxd}")
                shutil.copyfile(infra_pxd, src_init_pxd)


# =============================
# Define Cython Extensions
# =============================

cython_extension.extend(
    [
        Extension(
            name="cbase.env",
            sources=["cbase/env.pyx"],
            extra_compile_args=COMPILE_FLAGS,
            include_dirs=[REPO_ROOT]
        ),
        Extension(
            name="cbase.allocator_protocol.c_heap_allocator",
            sources=["cbase/allocator_protocol/c_heap_allocator.pyx"],
            extra_compile_args=COMPILE_FLAGS,
            include_dirs=[REPO_ROOT]
        ),
        Extension(
            name="cbase.allocator_protocol.c_shm_allocator",
            sources=["cbase/allocator_protocol/c_shm_allocator.pyx"],
            extra_compile_args=COMPILE_FLAGS,
            include_dirs=[REPO_ROOT]
        ),
        Extension(
            name="cbase.allocator_protocol.c_allocator_protocol",
            sources=["cbase/allocator_protocol/c_allocator_protocol.pyx"],
            extra_compile_args=COMPILE_FLAGS,
            include_dirs=[REPO_ROOT]
        ),
    ]
)

BuildExtWithConfig.remove_pxd()

try:
    ext_modules.extend(
        cythonize(
            cython_extension,
            annotate=WITH_ANNOTATION,
            compiler_directives={
                "language_level": "3",
                'embedsignature': True
            },
            force="--force" in sys.argv,
            nthreads=N_THREADS,
        )
    )
finally:
    BuildExtWithConfig.restore_pxd()

# =============================
# Define C Extensions
# =============================

ext_modules.extend(c_extensions)

# =============================
# Setup Function
# =============================


setup(
    name="PyCyBase",
    ext_modules=ext_modules,
    cmdclass={"build_ext": BuildExtWithConfig},
)
