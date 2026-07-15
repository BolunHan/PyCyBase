#!/usr/bin/env python3
"""
NT Test Runner — discovers and runs all test suites under tests/

Usage:
    python tests/nt_main.py                  # discover & run all tests
    python tests/nt_main.py -v               # verbose
    python tests/nt_main.py -q               # quiet (summary only)
    python tests/nt_main.py -f               # failfast
    python tests/nt_main.py <module>         # run specific module (e.g. bytemap)
"""

import os
import sys
import unittest


def main():
    # Ensure the project root is on sys.path so `cbase` is importable
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Parse CLI flags
    verbosity = 2 if "-v" in sys.argv else 0 if "-q" in sys.argv else 1
    failfast = "-f" in sys.argv

    # Filter out flags to get optional module names
    positional = [a for a in sys.argv[1:] if not a.startswith("-")]
    top_level = os.path.join(project_root, "tests")

    loader = unittest.TestLoader()

    if positional:
        suite = unittest.TestSuite()
        for name in positional:
            pkg = f"tests.{name}" if not name.startswith("tests.") else name
            suite.addTest(loader.loadTestsFromName(pkg))
    else:
        suite = loader.discover(top_level, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=verbosity, failfast=failfast)
    result = runner.run(suite)

    # Printable summary
    plural = "s" if result.testsRun != 1 else ""
    print(f"\n{'=' * 60}")
    print(f"Ran {result.testsRun} test{plural}  "
          f"OK={result.testsRun - len(result.failures) - len(result.errors)}  "
          f"FAIL={len(result.failures)}  "
          f"ERR={len(result.errors)}  "
          f"SKIP={len(result.skipped)}")
    print(f"{'=' * 60}")

    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
