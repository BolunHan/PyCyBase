"""Contract tests for the wheel's runtime Cython/Includes startup hook.

Expected behavior:
    - a missing link is created as ``Cython/Includes/cbase -> ../../cbase``;
    - a valid link is left alone;
    - a broken link is replaced;
    - without Cython installed nothing is created;
    - a real entry at the link path is reported and never removed.
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _cbase_cython_link


class TestEnsureCythonInclude(unittest.TestCase):
    """Contract: the hook maintains only its own relative symlink."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.site = self.root / 'site-packages'
        self.site.mkdir()
        self.includes = self.site / 'Cython' / 'Includes'
        self.includes.mkdir(parents=True)
        package = self.site / 'cbase'
        package.mkdir()
        source = Path(_cbase_cython_link.__file__).with_name('cbase') / 'cython_injection.py'
        shutil.copyfile(source, package / 'cython_injection.py')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def link(self) -> Path:
        """Return the link path under the fake environment's Cython/Includes."""
        return self.includes / 'cbase'

    def test_00_creates_relative_link(self) -> None:
        """The installed copy is linked with the expected relative target."""
        self.assertEqual(_cbase_cython_link.ensure_cython_include(self.site), 'injected')
        self.assertTrue(self.link().is_symlink())
        self.assertEqual(os.readlink(self.link()), '../../cbase')
        self.assertTrue(self.link().is_dir())

    def test_01_valid_link_is_left_alone(self) -> None:
        """A link that already resolves is reported and not rewritten."""
        _cbase_cython_link.ensure_cython_include(self.site)
        before = os.readlink(self.link())
        self.assertEqual(_cbase_cython_link.ensure_cython_include(self.site), 'already-injected')
        self.assertEqual(os.readlink(self.link()), before)

    def test_02_broken_link_is_replaced(self) -> None:
        """A dangling link is replaced with the correct target."""
        self.link().symlink_to('../../missing')
        self.assertFalse(self.link().exists())
        self.assertEqual(_cbase_cython_link.ensure_cython_include(self.site), 'injected')
        self.assertEqual(os.readlink(self.link()), '../../cbase')

    def test_03_without_cython_nothing_is_created(self) -> None:
        """An environment without Cython is left untouched."""
        shutil.rmtree(self.site / 'Cython')
        self.assertIsNone(_cbase_cython_link.ensure_cython_include(self.site))
        self.assertFalse((self.site / 'Cython').exists())

    def test_04_real_entry_is_reported(self) -> None:
        """A real directory at the link path is never removed."""
        self.link().mkdir()
        self.assertEqual(_cbase_cython_link.ensure_cython_include(self.site), 'conflict')
        self.assertTrue(self.link().is_dir())
        self.assertFalse(self.link().is_symlink())

    def test_05_missing_source_is_ignored(self) -> None:
        """Without an importable package no link is attempted."""
        shutil.rmtree(self.site / 'cbase')
        with mock.patch.object(_cbase_cython_link.importlib.util, 'find_spec', return_value=None):
            self.assertIsNone(_cbase_cython_link.ensure_cython_include(self.site))
        self.assertFalse(os.path.lexists(self.link()))


if __name__ == '__main__':
    unittest.main()
