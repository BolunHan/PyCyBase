"""Performance benchmark for InternString vs Python str.

Usage:
    python tests/intern_string/test_perf.py [--quick]

    --quick   Use smaller dataset for fast sanity check (default: full benchmark).
"""
import sys
import time

from cbase.intern_string.c_intern_string import IstrTestToolkit


def fmt_ns(ns: float) -> str:
    if ns < 1_000:
        return f'{ns:.1f} ns'
    elif ns < 1_000_000:
        return f'{ns / 1_000:.1f} µs'
    else:
        return f'{ns / 1_000_000:.1f} ms'


def main():
    quick = '--quick' in sys.argv

    if quick:
        print('=== Quick Benchmark (small dataset) ===')
        tk = IstrTestToolkit(
            buf_size=2 ** 20,    # 1 MiB
            n_seg=5_000,
            max_seg_len=64,
            n_iters=5,
        )
    else:
        print('=== Full Benchmark ===')
        tk = IstrTestToolkit(
            buf_size=2 ** 30,    # 1 GiB
            n_seg=100_000,
            max_seg_len=64,
            n_iters=10,
        )

    if tk.buf_size >= 2**30:
        print(f'  buf_size     = {tk.buf_size / 2**30:.2f} GiB')
    elif tk.buf_size >= 2**20:
        print(f'  buf_size     = {tk.buf_size / 2**20:.1f} MiB')
    else:
        print(f'  buf_size     = {tk.buf_size} bytes')
    print(f'  n_seg        = {tk.n_seg:,}')
    print(f'  max_seg_len  = {tk.max_seg_len}')
    print(f'  n_iters      = {tk.n_iters}')
    print()

    t0 = time.perf_counter()
    results = tk.run_test()
    wall = time.perf_counter() - t0
    print(f'  wall time    = {wall:.1f} s')
    print(f'  total key bytes = {results["total_key_bytes"]:,}')
    print()

    print('--- Per-operation latency (avg) ---')
    print(f'  {"istr_hash (fnv1a)":<28s} {fmt_ns(results["istr_hash_ns"])}')
    print(f'  {"istr_intern":<28s} {fmt_ns(results["istr_intern_ns"])}')
    print(f'  {"istr_lookup":<28s} {fmt_ns(results["istr_lookup_ns"])}')
    print(f'  {"istr_eq":<28s} {fmt_ns(results["istr_eq_ns"])}')
    print(f'  {"py_unicode (create)":<28s} {fmt_ns(results["py_unicode_ns"])}')
    print(f'  {"py_hash (str)":<28s} {fmt_ns(results["py_hash_ns"])}')
    print(f'  {"py_eq (str)":<28s} {fmt_ns(results["py_eq_ns"])}')
    print()

    # Speedup ratios
    if results['py_hash_ns'] > 0:
        ratio = results['py_hash_ns'] / max(results['istr_hash_ns'], 1e-9)
        print(f'  hash speedup:      istr {ratio:.1f}x faster than py str')
    if results['py_eq_ns'] > 0:
        ratio = results['py_eq_ns'] / max(results['istr_eq_ns'], 1e-9)
        print(f'  eq speedup:        istr {ratio:.1f}x faster than py str')
    if results['py_unicode_ns'] > 0:
        ratio = results['py_unicode_ns'] / max(results['istr_intern_ns'], 1e-9)
        print(f'  intern vs unicode: istr_intern {ratio:.1f}x vs py unicode create')

    print()
    print('--- Raw timings (seconds) ---')
    for k in sorted(results):
        if k.endswith('_s'):
            print(f'  {k:<30s} {results[k]:.6f}')
    print()
    print('OK')


if __name__ == '__main__':
    main()
