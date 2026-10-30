"""Contract tests for wheel RECORD-based uninstall cleanup.

Expected behavior:
    - record_cython_include appends ``Cython/Includes/<package>`` to a wheel's
      RECORD without touching the other entries;
    - a second call is a no-op;
    - the entry name can be overridden;
    - a wheel without RECORD or a missing wheel is left alone;
    - setup.py exposes the bdist_wheel and editable_wheel command classes.
"""
import tempfile
import unittest
import zipfile
from pathlib import Path

from cbase.cython_injection import record_cython_include


class TestRecordCythonInclude(unittest.TestCase):
    """Contract: a built wheel carries the uninstall entry in RECORD."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.wheel = self.root / 'demo-0.0.1-py3-none-any.whl'
        self.record = 'demo-0.0.1.dist-info/RECORD'
        with zipfile.ZipFile(self.wheel, 'w') as wheel:
            wheel.writestr('demo/__init__.py', '')
            wheel.writestr(self.record, f'demo/__init__.py,,\n{self.record},,\n')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def read(self, name: str) -> str:
        """Return a member of the test wheel as text."""
        with zipfile.ZipFile(self.wheel) as wheel:
            return wheel.read(name).decode('utf-8')

    def test_00_adds_entry(self) -> None:
        """The link path is appended to RECORD."""
        self.assertTrue(record_cython_include(self.wheel, 'demo'))
        text = self.read(self.record)
        self.assertIn('Cython/Includes/demo,,\n', text)
        self.assertIn('demo/__init__.py,,', text)

    def test_01_idempotent(self) -> None:
        """A second call does not duplicate the entry."""
        self.assertTrue(record_cython_include(self.wheel, 'demo'))
        self.assertFalse(record_cython_include(self.wheel, 'demo'))
        self.assertEqual(self.read(self.record).count('Cython/Includes/demo,,'), 1)

    def test_02_custom_name(self) -> None:
        """The Cython/Includes entry name can be overridden."""
        self.assertTrue(record_cython_include(self.wheel, 'demo', name='alias'))
        self.assertIn('Cython/Includes/alias,,', self.read(self.record))

    def test_03_no_record(self) -> None:
        """A wheel without RECORD is left unchanged and reports False."""
        wheel = self.root / 'bare-0.0.1-py3-none-any.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('bare/__init__.py', '')
        self.assertFalse(record_cython_include(wheel, 'bare'))
        with zipfile.ZipFile(wheel) as archive:
            self.assertEqual(archive.namelist(), ['bare/__init__.py'])

    def test_04_missing_wheel(self) -> None:
        """A missing wheel reports False instead of raising."""
        self.assertFalse(record_cython_include(self.root / 'missing.whl', 'demo'))

    def test_05_preserves_other_members(self) -> None:
        """Rewriting the wheel keeps the payload and RECORD files."""
        self.assertTrue(record_cython_include(self.wheel, 'demo'))
        with zipfile.ZipFile(self.wheel) as archive:
            self.assertIn('demo/__init__.py', archive.namelist())
            self.assertIn(self.record, archive.namelist())


class TestSetupWiring(unittest.TestCase):
    """Contract: setup.py registers the wheel commands that record the link."""

    def test_00_wheel_commands_present(self) -> None:
        """Both wheel-building commands are subclassed."""
        import setup

        self.assertTrue(issubclass(setup.BdistWheelWithCythonLink, setup._bdist_wheel))
        self.assertIsNotNone(setup._editable_wheel)
        self.assertTrue(issubclass(setup.EditableWheelWithCythonLink, setup._editable_wheel))

    def test_01_loader_exposes_helper(self) -> None:
        """The file-path loader used in clean builds exposes the helper."""
        import setup

        module = setup._load_cython_injection()
        self.assertTrue(callable(module.record_cython_include))


if __name__ == '__main__':
    unittest.main()
