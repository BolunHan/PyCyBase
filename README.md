# PyCyBase

Common C / Cython dual interfaces for Python HFT Projects.

## Overview

This package provides low-level allocator infrastructure shared across HFT projects:

- **c_allocator_protocol** — Unified memory allocation protocol supporting heap, shared memory (SHM), and raw malloc backends with ref-counting and vigilant mode.
- **c_shm_allocator** — POSIX shared-memory backed page allocator with fixed-address virtual region mapping for cross-process pointer stability.
- **c_heap_allocator** — In-process heap allocator with free-list reuse and auto-growing pages.

## Installation

```bash
pip install -e .
```

## Usage

```python
from cbase.allocator_protocol.c_allocator_protocol import AllocatorProtocol, AP_SHARED

with AP_SHARED:
    alloc = AllocatorProtocol(1024)
    alloc.buf[0] = b'x'
```

## License

Proprietary.
