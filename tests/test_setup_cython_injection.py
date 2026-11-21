"""Contract tests for the setup.py injection hook.

The loader and the ``BuildExtWithConfig`` hook are exercised without building
extensions or touching the real environment.

Expected behavior:
    - the injection module is loaded by file path and never imports cbase;
    - wheel builds pass ``editable=False``;
    - PEP 660 editable builds pass ``editable=True``;
    - a direct ``build_ext --inplace`` skips injection entirely;
    - a successful link is printed with its relative target;
    - a missing Cython and an injection exception are reported, never raised.
"""
import builtins
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import setup


class _FakeBuild:
    """Minimal stand-in for BuildExtWithConfig."""

    inplace = False
    inject_cython_includes = setup.BuildExtWithConfig.inject_cython_includes


class TestLoader(unittest.TestCase):
    """Contract: setup.py never imports the compiled cbase package."""

    def test_00_loads_module_by_path(self) -> None:
        """The loader returns the module with its public entry points."""
        module = setup._load_cython_injection()
        self.assertEqual(module.__name__, '_cbase_cython_injection')
        self.assertTrue(callable(module.inject_cython_includes))
        self.assertTrue(callable(module.cython_injection_path))

    def test_01_loader_does_not_import_cbase(self) -> None:
        """Importing cbase during setup would fail in a clean source tree."""
        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name == 'cbase' or name.startswith('cbase.'):
                raise AssertionError('setup.py must not import cbase')
            return real_import(name, *args, **kwargs)

        with mock.patch('builtins.__import__', side_effect=guarded):
            module = setup._load_cython_injection()
        self.assertTrue(callable(module.inject_cython_includes))


class TestHook(unittest.TestCase):
    """Contract: the hook reports status and never aborts a build."""

    @staticmethod
    def _module(status: str, link: Path | None):
        class FakeModule:
            INJECTED = 'injected'
            ALREADY_INJECTED = 'already-injected'
            SKIPPED_NO_CYTHON = 'skipped-no-cython'

            @staticmethod
            def inject_cython_includes(package, **kwargs):
                FakeModule.calls = {'package': package, **kwargs}
                return status

            @staticmethod
            def cython_injection_path(package, **kwargs):
                return link

        FakeModule.calls = {}
        return FakeModule

    def test_00_editable_wheel_passes_editable(self) -> None:
        """PEP 660 editable builds link the source tree."""
        module = self._module('injected', Path('/fake/Cython/Includes/cbase'))

        class EditableBuild(_FakeBuild):
            inplace = True

        with (
            mock.patch.object(setup, '_load_cython_injection', return_value=module),
            mock.patch.object(setup.os, 'readlink', return_value='../../../../cbase'),
            mock.patch.object(setup.sys, 'argv', ['setup.py', 'editable_wheel', '--dist-dir', '/tmp']),
            redirect_stdout(io.StringIO()) as out,
        ):
            EditableBuild().inject_cython_includes()
        self.assertEqual(module.calls['package'], 'cbase')
        self.assertTrue(module.calls['editable'])
        self.assertIn('Cython/Includes/cbase -> ../../../../cbase', out.getvalue())

    def test_01_wheel_build_passes_not_editable(self) -> None:
        """Wheel builds link the installed copy."""
        module = self._module('injected', Path('/fake/Cython/Includes/cbase'))

        with (
            mock.patch.object(setup, '_load_cython_injection', return_value=module),
            mock.patch.object(setup.os, 'readlink', return_value='../../cbase'),
            redirect_stdout(io.StringIO()),
        ):
            _FakeBuild().inject_cython_includes()
        self.assertFalse(module.calls['editable'])

    def test_02_inplace_build_is_skipped(self) -> None:
        """A direct ``build_ext --inplace`` leaves Cython/Includes untouched."""
        loader = mock.Mock(side_effect=AssertionError('loader must not run'))

        class InplaceBuild(_FakeBuild):
            inplace = True

        with (
            mock.patch.object(setup, '_load_cython_injection', loader),
            mock.patch.object(setup.sys, 'argv', ['setup.py', 'build_ext', '--inplace']),
            redirect_stdout(io.StringIO()) as out,
        ):
            InplaceBuild().inject_cython_includes()
        loader.assert_not_called()
        self.assertIn('in-place build: Cython include injection skipped', out.getvalue())

    def test_03_missing_cython_is_reported(self) -> None:
        """A skipped injection prints the reason instead of a link."""
        module = self._module('skipped-no-cython', None)
        with (
            mock.patch.object(setup, '_load_cython_injection', return_value=module),
            redirect_stdout(io.StringIO()) as out,
        ):
            _FakeBuild().inject_cython_includes()
        self.assertIn('Cython is not installed in the target environment', out.getvalue())

    def test_04_exception_is_warned(self) -> None:
        """An injection exception never escapes the build hook."""
        with (
            mock.patch.object(setup, '_load_cython_injection', side_effect=RuntimeError('boom')),
            redirect_stdout(io.StringIO()) as out,
        ):
            _FakeBuild().inject_cython_includes()
        self.assertIn('Warning: Cython include injection failed: boom', out.getvalue())


if __name__ == '__main__':
    unittest.main()
