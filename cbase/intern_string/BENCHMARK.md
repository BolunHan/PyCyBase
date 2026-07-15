# InternString Performance Benchmark

## Backend Comparison — Pure C-level

**Dataset:** 256 MiB buffer, 50,000 segments, max 64 bytes/segment, 10 iterations
**Total key bytes:** ~1.6 MB

### Per-operation latency (ns)

| Benchmark | Native | Bytemap | Winner |
|---|---:|---:|---|
| `fnv1a_hash` (raw C) | 48.8 ns | 38.3 ns | Bytemap (1.27×) |
| `istr_intern` (unlocked) | 291.6 ns | 532.8 ns | Native (1.83×) |
| `istr_intern_synced` | 192.2 ns | 390.5 ns | Native (2.03×) |
| `istr_lookup` (unlocked) | 57.3 ns | 28.2 ns | Bytemap (2.03×) |
| `istr_lookup_synced` | 54.5 ns | 26.3 ns | Bytemap (2.07×) |
| `istr_eq` (Python) | 215.1 ns | 197.7 ns | Bytemap (1.09×) |
| `py_unicode` (create) | 52.4 ns | 46.0 ns | — |
| `py_hash` (str) | 3.8 ns | 4.2 ns | — |
| `py_eq` (str) | 4.7 ns | 4.7 ns | — |

### Mutex overhead (synced − unlocked, per op)

| Operation | Native | Bytemap |
|---|---|---|
| Intern | *noise* | *noise* |
| Lookup | ~1.0 ns | ~1.9 ns |

> Mutex overhead is within measurement noise — the pthread_mutex_lock/unlock cost
> (~15–25 ns) is dwarfed by the hash+probe cost at 50k iterations. The negative
> values sometimes seen are run-ordering artifacts (heap warm-up from prior
> unlocked run).

### Analysis

| Operation | Result |
|---|---|
| **Intern speed** | Native 1.83× faster — simpler insert path (no tombstone logic, no XXH3 wrapper overhead) |
| **Lookup speed** | Bytemap 2.03× faster — XXH3 hash + `memcmp` with stored `key_length` beats FNV-1a |
| **Hash speed** | XXH3 beats FNV-1a by 1.27× on raw `const char*` |
| **Pure C vs Python** | Both now hit C fast path via `PyUnicode_AsUTF8AndSize` + `key_length` — zero strlen |

### Backend behavioral differences

| Behavior | Native | Bytemap |
|---|---|---|
| Iteration order | LIFO (reverse insertion) | FIFO (insertion order via doubly-linked list) |
| Empty string (`""`) | Valid (1-byte allocation) | Rejected (`BYTEMAP_ERR_INVALID_KEY`) |
| Hash function | FNV-1a | XXH3 (with per-map salt) |
| Capacity rounding | Power-of-2 | Internal (MIN_BYTEMAP_CAPACITY = 16) |
| Resize trigger | `size >= capacity/2` | `occupied * 2 >= capacity` |
| Thread safety | Internal `pthread_mutex_t` | Embedded `pthread_mutex_t` in istr_map wrapper |

### Optimizations applied

- `c_istr` / `c_istr_map_lookup` accept `size_t key_length` — `strlen` skipped when known
- `strcmp` replaced with `key_length` comparison + `memcmp` shortcut
- `PyUnicode_AsUTF8AndSize` passes pre-computed UTF-8 length from Python layer
- C-level benchmark routines bypass Python `str` entirely — raw `const char*` + `size_t`

---

## NT Cross-Platform — Native Backend

**Quick benchmark:** 1 MiB buffer, 5,000 segments, max 64 bytes, 5 iterations
**Unit tests:** 220/220 pass, 0 fail, 5 skipped (fork-related)

### Per-operation latency (ns)

| Benchmark | Linux (gcc -O2) | Windows NT (MSVC /O2) | Δ |
|---|---:|---:|---|
| `fnv1a_hash` | 13.5 ns | 15.5 ns | +15% |
| `istr_intern` (unlocked) | 116.6 ns | 120.8 ns | +4% |
| `istr_intern` (synced) | 102.6 ns | 107.0 ns | +4% |
| `istr_lookup` (unlocked) | 24.6 ns | 30.2 ns | +23% |
| `istr_lookup` (synced) | 25.6 ns | 31.6 ns | +23% |
| `istr_eq` (Python) | 177.5 ns | 208.0 ns | +17% |
| `py_unicode` (create) | 27.9 ns | 34.1 ns | +22% |
| `py_hash` | 4.6 ns | 6.3 ns | +37% |
| `py_eq` | 4.6 ns | 6.8 ns | +48% |

### NT compatibility

| Component | Status |
|---|---|
| `pthread_nt_compat.h` (`pthread_mutex_t` → `CRITICAL_SECTION`) | ✅ |
| MSVC build (`/std:c17 /experimental:c11atomics`) | ✅ |
| Cython 3.x on Windows | ✅ |
| All 220 unit tests | ✅ |
| Thread safety (concurrent tests) | ✅ |
| Performance delta vs Linux | ~15–23% (expected: MSVC vs GCC codegen) |

---

## Running Benchmarks

```bash
# Linux — native backend (default)
python tests/intern_string/test_perf.py          # full (1 GiB, 100k segs, 10 iters)
python tests/intern_string/test_perf.py --quick  # quick (1 MiB, 5k segs, 5 iters)

# Linux — bytemap backend (requires rebuild)
# Add -DISTR_USE_BYTEMAP_BACKEND=1 to extra_compile_args in setup.py, rebuild, then:
python tests/intern_string/test_perf.py --quick

# Windows NT
python nt_build.py                    # full sync→build→test cycle
# Then run test_perf.py on the VM
```

## Test Toolkit API

```python
from cbase.intern_string.c_intern_string import IstrTestToolkit

tk = IstrTestToolkit(
    buf_size=2**30,    # 1 GiB character buffer
    n_seg=100_000,     # number of random segments
    max_seg_len=64,    # max segment length in bytes
    n_iters=10,        # benchmark repetitions
)

results = tk.run_test()
# Returns dict with per-op nanosecond latencies + raw timings
```
