# PyCyBase

[![docs](https://github.com/BolunHan/PyCyBase/actions/workflows/build-page-docs.yml/badge.svg)](https://github.com/BolunHan/PyCyBase/actions/workflows/build-page-docs.yml)
[![pypi-linux](https://github.com/BolunHan/PyCyBase/actions/workflows/publish-posix-to-pypi.yml/badge.svg)](https://github.com/BolunHan/PyCyBase/actions/workflows/publish-posix-to-pypi.yml)
[![pypi-windows](https://github.com/BolunHan/PyCyBase/actions/workflows/publish-nt-to-pypi.yml/badge.svg)](https://github.com/BolunHan/PyCyBase/actions/workflows/publish-nt-to-pypi.yml)

Common C / Cython dual interfaces for Python HFT Projects.

## Overview

Low-level allocator infrastructure shared across HFT projects:

- **Allocator Protocol** — Pluggable memory allocation with heap, shared-memory (SHM), and raw `malloc` backends. Ref-counting, vigilant mode, thread-safety controls.
- **Heap Allocator** — In-process allocator with free-list reuse and auto-growing pages.
- **SHM Allocator** — POSIX shared-memory page allocator with fixed-address virtual region mapping for cross-process pointer stability.
- **ByteMap** — Fast xxHash3-backed hash maps for byte-string keys (ByteMap, ByteMapEx, bound variants).
- **Intern String** — FNV-1a-hashed string interning with SHM-backed cross-process pools. 1.7–2.2× speedup over Python `str`.

## Quick Start

```python
from cbase.allocator_protocol import AllocatorProtocol, AP_SHARED

with AP_SHARED:
    alloc = AllocatorProtocol(1024)
    alloc.buf[0] = b'x'
```

```python
from cbase.intern_string import POOL

aapl = POOL.istr("AAPL")
assert aapl is POOL.istr("AAPL")  # Identity — string deduplication
```

```python
from cbase.bytemap import ByteMap

bm = ByteMap()
bm[b"ticker"] = b"AAPL"
assert bm[b"ticker"] == b"AAPL"
```

## Build & Install

PyCyBase is a Cython extension package — it **cannot** be used with `pip install -e .` (editable mode breaks Cython `.pxd` resolution for downstream projects).

### POSIX (Linux / macOS)

```bash
# Build extensions in-place, then install
./build.sh -i

# Or equivalently:
make build && pip install -U . --no-build-isolation

# Or step by step:
python setup.py build_ext --inplace --verbose --force
pip install -U . --no-build-isolation
```

**Build script reference:**

| Command | Effect |
|---------|--------|
| `./build.sh` | Clean + build in-place |
| `./build.sh -i` | Clean + build + `pip install .` |
| `./build.sh -r` | Clean + build + force-reinstall |
| `./build.sh -c` | Clean only (no build) |
| `./build.sh -a` | Deep clean (remove `.c` and `.so` files) |
| `./build.sh -l` | List all compile-time macros |
| `./build.sh -v /path/to/venv` | Use a specific venv |
| `make` or `make build` | Clean + build |
| `make install` | Build + `pip install .` |
| `make reinstall` | Build + force-reinstall |
| `make list-args` | List compile-time macros |

### Windows (NT)

```powershell
# Local build
.\build.ps1 -VenvPath "C:\Users\...\venv_313"

# Remote build (from Linux host):
python nt_build.py
```

### Compile-Time Macros

Override any macro at build time via environment variable:

```bash
DEBUG=1 ./build.sh         # Enable debug mode
DEBUG=1 make build          # Same via Makefile
```

List all available macros and defaults:

```bash
./build.sh -l               # Auto-generates macros.json via probe.py
make list-args
python probe.py             # Run the probe directly
```

Key macros (see `macros.json` for full list):

| Macro | Default | Description |
|-------|---------|-------------|
| `AP_ALLOC_VIGILANT` | `1` | Enable bounds/canary checks |
| `AP_ALLOC_WITH_LOCK` | `1` | Thread-safety via pthread mutex |
| `AP_ALLOC_WITH_SHM` | `0` | Default to SHM allocator |
| `AP_ALLOC_WITH_FREELIST` | `1` | Free-list reuse |
| `AP_HEAP_AUTOPAGE_CAPACITY` | `64 KiB` | Default heap page size |
| `AP_HEAP_AUTOPAGE_CAPACITY_MAX` | `16 MiB` | Max heap page size |
| `AP_SHM_AUTOPAGE_CAPACITY` | `64 KiB` | Default SHM page size |
| `AP_SHM_ALLOCATOR_DEFAULT_REGION_SIZE` | `128 GiB` | SHM virtual region |

### Using `get_include()` in Downstream Projects

```python
from setuptools import setup, Extension
from Cython.Build import cythonize
import cbase

ext = Extension(
    "my_module",
    sources=["my_module.pyx"],
    include_dirs=cbase.get_include(),
)
setup(ext_modules=cythonize([ext]))
```

## Modules

| Module | Description |
|--------|-------------|
| `cbase.env` | `EnvConfigContext` — context manager for temporary config changes |
| `cbase.allocator_protocol` | `AllocatorProtocol`, `AllocatorConfigContext`, AP sentinels |
| `cbase.allocator_protocol.c_heap_allocator` | In-process heap allocator with free-list |
| `cbase.allocator_protocol.c_shm_allocator` | POSIX shared-memory page allocator |
| `cbase.bytemap.c_bytemap` | xxHash3-backed hash maps |
| `cbase.intern_string.c_intern_string` | FNV-1a-hashed string interning |
| `cbase.backports.pylong` | Python int ↔ 128-bit integer (uint128_t/int128_t) backport |
| `cbase.backports.pydict` | PyDict_Pop backport for pre-3.13 Python |

## Documentation

```bash
pip install sphinx furo
cd docs
sphinx-build -M html . _build
# Or with the project venv:
~/Projects/venv_313/bin/sphinx-build -M html . _build
```

Open `docs/_build/html/index.html`.

Online: https://bolunhan.github.io/PyCyBase/

## License

Proprietary.
