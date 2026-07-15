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
    print(f'  n_unique     = {tk.n_unique:,}')
    print(f'  n_ops        = {tk.n_ops:,}')
    print(f'  max_seg_len  = {tk.max_seg_len}')
    print(f'  n_iters      = {tk.n_iters}')
    print()

    t0 = time.perf_counter()
    results = tk.run_test()
    wall = time.perf_counter() - t0
    print(f'  wall time    = {wall:.1f} s')
    print(f'  total key bytes = {results["total_key_bytes"]:,}')
    print()

    print('--- All-miss (fresh pool, every string new) ---')
    print(f'  {"istr_intern (unlocked)":<28s} {fmt_ns(results["istr_intern_ns"])}')
    print(f'  {"istr_intern (synced)":<28s} {fmt_ns(results["istr_intern_synced_ns"])}')
    print(f'  {"istr_lookup (unlocked)":<28s} {fmt_ns(results["istr_lookup_ns"])}')
    print(f'  {"istr_lookup (synced)":<28s} {fmt_ns(results["istr_lookup_synced_ns"])}')
    print(f'  {"py_unicode (create)":<28s} {fmt_ns(results["py_unicode_ns"])}')
    print()
    print(f'--- Limited pool (n_unique={results["n_unique"]:,}, n_ops={results["n_ops"]:,}) ---')
    print(f'  {"istr_limited (unlocked)":<28s} {fmt_ns(results["istr_limited_ns"])}')
    print(f'  {"istr_limited (synced)":<28s} {fmt_ns(results["istr_limited_synced_ns"])}')
    print(f'  {"  mutex overhead":<28s} {fmt_ns(results["istr_limited_mutex_ns"])}')
    print(f'  {"py_unicode_limited":<28s} {fmt_ns(results["py_unicode_limited_ns"])}')
    if results['py_unicode_limited_ns'] > 0:
        ratio = results['py_unicode_limited_ns'] / max(results['istr_limited_ns'], 1e-9)
        print(f'  {"  istr vs py_unicode":<28s} istr is {ratio:.1f}x {"faster" if ratio > 1 else "slower"}')
    print()
    print(f'--- Other ---')
    print(f'  {"istr_hash (fnv1a)":<28s} {fmt_ns(results["istr_hash_ns"])}')
    print(f'  {"istr_eq (Python ==)":<28s} {fmt_ns(results["istr_eq_ns"])}')
    print(f'  {"py_hash":<28s} {fmt_ns(results["py_hash_ns"])}')
    print(f'  {"py_eq":<28s} {fmt_ns(results["py_eq_ns"])}')
    print()
    print('--- Raw timings (seconds) ---')
    for k in sorted(results):
        if k.endswith('_s'):
            print(f'  {k:<30s} {results[k]:.6f}')
    print()
    print('OK')


if __name__ == '__main__':
    main()
