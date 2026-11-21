"""Contract tests for the Cython/Includes startup hook shipped in wheels.

Expected behavior:
    - the bootstrap module and its ``.pth`` are added to the wheel;
    - every member listed in ``RECORD`` exists in the archive, with the added
      members carrying a real hash and size (``auditwheel`` opens each one);
    - no ``Cython/Includes`` entry is written into the wheel's ``RECORD``;
    - a second call is a no-op and leaves the wheel bytes untouched;
    - a wheel without ``RECORD`` or a missing wheel is left alone;
    - setup.py registers the wheel commands that ship the hook.
"""
import base64
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from cbase.cython_injection import ensure_wheel_site_hook


class TestEnsureWheelSiteHook(unittest.TestCase):
    """Contract: a built wheel carries everything needed to inject on import."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.wheel = self.root / 'demo-0.0.1-py3-none-any.whl'
        self.record = 'demo-0.0.1.dist-info/RECORD'
        self.module = self.root / '_demo_link.py'
        self.module.write_text('# demo startup hook\n', encoding='utf-8')
        with zipfile.ZipFile(self.wheel, 'w') as wheel:
            wheel.writestr('demo/__init__.py', '')
            wheel.writestr(self.record, f'demo/__init__.py,,\n{self.record},,\n')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def names(self) -> set[str]:
        """Return the members of the test wheel."""
        with zipfile.ZipFile(self.wheel) as wheel:
            return set(wheel.namelist())

    def read(self, name: str) -> bytes:
        """Return a member of the test wheel as bytes."""
        with zipfile.ZipFile(self.wheel) as wheel:
            return wheel.read(name)

    def rows(self) -> dict[str, list[str]]:
        """Return the wheel's RECORD rows keyed by path."""
        text = self.read(self.record).decode('utf-8')
        return {line.split(',', 1)[0]: line.split(',') for line in text.splitlines()}

    def test_00_adds_module_and_pth(self) -> None:
        """Both startup hook members are present and the .pth imports the module."""
        self.assertTrue(ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link'))
        self.assertIn('_demo_link.py', self.names())
        self.assertEqual(self.read('_demo_link.pth'), b'import _demo_link\n')

    def test_01_record_covers_every_member(self) -> None:
        """Every archive member is listed; added members carry hash and size."""
        ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link')
        rows = self.rows()
        self.assertEqual(set(rows), self.names())
        for name in ('_demo_link.py', '_demo_link.pth'):
            data = self.read(name)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=')
            self.assertEqual(rows[name][1], f'sha256={digest.decode("ascii")}')
            self.assertEqual(int(rows[name][2]), len(data))

    def test_02_does_not_record_an_external_link(self) -> None:
        """Nothing outside the archive may appear in RECORD (auditwheel fails)."""
        ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link')
        self.assertFalse(any(name.startswith('Cython/Includes') for name in self.rows()))

    def test_03_idempotent(self) -> None:
        """A second call does not duplicate members or rewrite the wheel."""
        ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link')
        before = self.wheel.read_bytes()
        self.assertTrue(ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link'))
        self.assertEqual(self.wheel.read_bytes(), before)
        self.assertEqual(sum(1 for name in self.names() if name == '_demo_link.py'), 1)

    def test_04_no_record(self) -> None:
        """A wheel without RECORD is left unchanged and reports False."""
        wheel = self.root / 'bare-0.0.1-py3-none-any.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('bare/__init__.py', '')
        self.assertFalse(ensure_wheel_site_hook(wheel, self.module, module_name='_demo_link'))
        with zipfile.ZipFile(wheel) as archive:
            self.assertEqual(archive.namelist(), ['bare/__init__.py'])

    def test_05_missing_wheel(self) -> None:
        """A missing wheel reports False instead of raising."""
        self.assertFalse(ensure_wheel_site_hook(self.root / 'missing.whl', self.module))

    def test_06_missing_source(self) -> None:
        """A missing bootstrap source reports False instead of raising."""
        self.assertFalse(ensure_wheel_site_hook(self.wheel, self.root / 'missing.py'))

    def test_07_preserves_other_members(self) -> None:
        """Rewriting the wheel keeps the payload and RECORD files."""
        ensure_wheel_site_hook(self.wheel, self.module, module_name='_demo_link')
        with zipfile.ZipFile(self.wheel) as archive:
            self.assertIn('demo/__init__.py', archive.namelist())
            self.assertIn(self.record, archive.namelist())


class TestSetupWiring(unittest.TestCase):
    """Contract: setup.py registers the wheel commands that ship the hook."""

    def test_00_wheel_commands_present(self) -> None:
        """Both wheel-building commands are subclassed."""
        import setup

        self.assertTrue(issubclass(setup.BdistWheelWithCythonLink, setup._bdist_wheel))
        self.assertIsNotNone(setup._editable_wheel)
        self.assertTrue(issubclass(setup.EditableWheelWithCythonLink, setup._editable_wheel))

    def test_01_hook_source_exists(self) -> None:
        """The module setup.py ships matches the reserved hook name."""
        import setup

        module = setup._load_cython_injection()
        source = Path(setup.REPO_ROOT) / f'{module.SITE_HOOK_MODULE}.py'
        self.assertTrue(source.is_file())


if __name__ == '__main__':
    unittest.main()
