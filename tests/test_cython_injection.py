"""Contract tests for cbase.cython_injection.

Every case runs against a disposable fake environment, so the interpreter's
real site-packages is never modified.

Expected behavior:
    - the target site-packages is found from a venv root, an explicit
      site-packages path, or VIRTUAL_ENV;
    - injection is skipped when Cython is absent from the target environment;
    - non-editable installs link to site-packages/<package> with the relative
      target ../../<package>;
    - editable installs link to the source tree;
    - stale symlinks are replaced, real directories conflict unless forced;
    - uninject removes only symlinks.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cbase.cython_injection import (
    ALREADY_INJECTED,
    CONFLICT,
    INJECTED,
    NOT_INJECTED,
    SKIPPED_NO_CYTHON,
    SKIPPED_NO_ENVIRONMENT,
    SKIPPED_NO_PACKAGE,
    UNINJECTED,
    CythonInjectionError,
    cython_injection_path,
    cython_injection_status,
    inject_cython_includes,
    resolve_cython_includes,
    resolve_site_packages,
    uninject_cython_includes,
)


class _FakeEnv(unittest.TestCase):
    """Build a disposable POSIX-layout environment with Cython installed."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.venv = self.root / 'venv'
        self.site_packages = self.venv / 'lib' / 'python3.13' / 'site-packages'
        self.includes = self.site_packages / 'Cython' / 'Includes'
        self.includes.mkdir(parents=True)
        self.link = self.includes / 'cbase'
        self.package_source = self.root / 'src' / 'cbase'
        self.package_source.mkdir(parents=True)
        (self.package_source / '__init__.pxd').write_text('')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def inject(self, **kwargs) -> str:
        """Inject with this fake environment as the target."""
        return inject_cython_includes(env=self.venv, **kwargs)


class TestResolveSitePackages(_FakeEnv):
    """Contract: the target site-packages is discovered deterministically."""

    def test_00_venv_root(self) -> None:
        """A venv root resolves through lib/python*/site-packages."""
        self.assertEqual(resolve_site_packages(self.venv), self.site_packages)

    def test_01_site_packages_direct(self) -> None:
        """An explicit site-packages path is returned unchanged."""
        self.assertEqual(resolve_site_packages(self.site_packages), self.site_packages)

    def test_02_windows_layout(self) -> None:
        """The Windows Lib/site-packages layout is recognized."""
        venv = self.root / 'win-venv'
        site_packages = venv / 'Lib' / 'site-packages'
        (site_packages / 'Cython' / 'Includes').mkdir(parents=True)
        self.assertEqual(resolve_site_packages(venv), site_packages)

    def test_03_interpreter_beats_virtual_env(self) -> None:
        """The running interpreter wins over a stale VIRTUAL_ENV."""
        other = self.root / 'other-venv' / 'lib' / 'python3.13' / 'site-packages'
        (other / 'Cython' / 'Includes').mkdir(parents=True)
        paths = {'purelib': str(self.site_packages), 'platlib': str(self.site_packages)}
        with (
            mock.patch('cbase.cython_injection.sysconfig.get_paths', return_value=paths),
            mock.patch.dict(os.environ, {'VIRTUAL_ENV': str(self.root / 'other-venv'), 'CONDA_PREFIX': ''}),
        ):
            self.assertEqual(resolve_site_packages(), self.site_packages)

    def test_04_virtual_env_fallback(self) -> None:
        """VIRTUAL_ENV is used when the running interpreter has no candidates."""
        missing = {'purelib': str(self.root / 'missing-purelib'), 'platlib': str(self.root / 'missing-platlib')}
        with (
            mock.patch('cbase.cython_injection.sysconfig.get_paths', return_value=missing),
            mock.patch('cbase.cython_injection.site.ENABLE_USER_SITE', False),
            mock.patch.dict(os.environ, {'VIRTUAL_ENV': str(self.venv), 'CONDA_PREFIX': ''}),
        ):
            self.assertEqual(resolve_site_packages(), self.site_packages)

    def test_05_missing_environment(self) -> None:
        """A nonexistent environment yields None."""
        self.assertIsNone(resolve_site_packages(self.root / 'missing'))

    def test_06_cython_includes_lookup(self) -> None:
        """Cython/Includes is found only when it exists."""
        self.assertEqual(resolve_cython_includes(self.site_packages), self.includes)
        bare = self.root / 'bare'
        bare.mkdir()
        self.assertIsNone(resolve_cython_includes(bare))


class TestInjectCythonIncludes(_FakeEnv):
    """Contract: the Cython/Includes entry mirrors the installation mode."""

    def test_00_non_editable_links_installed_copy(self) -> None:
        """A wheel install links to site-packages/<package>."""
        installed = self.site_packages / 'cbase'
        installed.mkdir()
        status = self.inject(package='cbase', editable=False)
        self.assertEqual(status, INJECTED)
        self.assertTrue(self.link.is_symlink())
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))
        self.assertEqual(Path(os.path.realpath(self.link)), installed.resolve())

    def test_01_editable_links_source(self) -> None:
        """An editable install links to the source tree."""
        status = self.inject(package='cbase', source=self.package_source, editable=True)
        self.assertEqual(status, INJECTED)
        self.assertEqual(Path(os.path.realpath(self.link)), self.package_source.resolve())

    def test_02_missing_cython_skips(self) -> None:
        """No Cython in the target environment means no link."""
        venv = self.root / 'bare-venv'
        (venv / 'lib' / 'python3.13' / 'site-packages').mkdir(parents=True)
        status = inject_cython_includes('cbase', source=self.package_source, env=venv, editable=True)
        self.assertEqual(status, SKIPPED_NO_CYTHON)
        self.assertFalse((venv / 'lib' / 'python3.13' / 'site-packages' / 'Cython' / 'Includes').exists())

    def test_03_idempotent(self) -> None:
        """Repeating the injection reports the link as already current."""
        (self.site_packages / 'cbase').mkdir()
        self.assertEqual(self.inject(package='cbase', editable=False), INJECTED)
        self.assertEqual(self.inject(package='cbase', editable=False), ALREADY_INJECTED)
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))

    def test_04_replaces_stale_symlink(self) -> None:
        """A symlink that points elsewhere is repointed."""
        (self.site_packages / 'cbase').mkdir()
        os.symlink(self.package_source, self.link, target_is_directory=True)
        self.assertEqual(self.inject(package='cbase', editable=False), INJECTED)
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))

    def test_05_real_directory_requires_force(self) -> None:
        """A real directory conflicts unless force=True."""
        (self.site_packages / 'cbase').mkdir()
        self.link.mkdir()
        (self.link / 'keep.pxd').write_text('')
        self.assertEqual(self.inject(package='cbase', editable=False), CONFLICT)
        self.assertTrue((self.link / 'keep.pxd').is_file())

        self.assertEqual(self.inject(package='cbase', editable=False, force=True), INJECTED)
        self.assertTrue(self.link.is_symlink())
        self.assertFalse((self.link / 'keep.pxd').exists())

    def test_06_editable_without_source_skips(self) -> None:
        """Editable mode skips when no source directory can be resolved."""
        status = self.inject(package='package_that_does_not_exist_xyz', editable=True)
        self.assertEqual(status, SKIPPED_NO_PACKAGE)

    def test_07_missing_explicit_source_raises(self) -> None:
        """An explicit source path that does not exist is an error."""
        with self.assertRaises(CythonInjectionError):
            self.inject(package='cbase', source=self.root / 'missing', editable=True)

    def test_08_auto_selects_source_when_not_installed(self) -> None:
        """Without an installed copy, auto mode falls back to the source tree."""
        self.assertEqual(self.inject(package='cbase', source=self.package_source), INJECTED)
        self.assertEqual(Path(os.path.realpath(self.link)), self.package_source.resolve())

    def test_09_auto_prefers_installed_copy(self) -> None:
        """Auto mode uses the installed copy when it exists."""
        (self.site_packages / 'cbase').mkdir()
        self.assertEqual(self.inject(package='cbase', source=self.package_source), INJECTED)
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))

    def test_10_custom_link_name(self) -> None:
        """The Cython/Includes entry name can be overridden."""
        (self.site_packages / 'cbase').mkdir()
        status = self.inject(package='cbase', editable=False, name='cbase_alias')
        self.assertEqual(status, INJECTED)
        alias = self.includes / 'cbase_alias'
        self.assertTrue(alias.is_symlink())
        self.assertEqual(os.readlink(alias), os.path.join('..', '..', 'cbase'))

    def test_11_strict_raises_on_skip(self) -> None:
        """strict=True turns a skip into an exception."""
        venv = self.root / 'bare-venv-strict'
        (venv / 'lib' / 'python3.13' / 'site-packages').mkdir(parents=True)
        with self.assertRaises(CythonInjectionError):
            inject_cython_includes('cbase', env=venv, editable=False, strict=True)

    def test_12_symlinked_environment_root(self) -> None:
        """Relative links stay correct when the environment root is a symlink."""
        alias = self.root / 'venv-link'
        alias.symlink_to(self.venv, target_is_directory=True)

        status = inject_cython_includes('cbase', source=self.package_source, env=alias, editable=True)
        self.assertEqual(status, INJECTED)
        self.assertEqual(Path(os.path.realpath(self.link)), self.package_source.resolve())

        installed = self.site_packages / 'cbase'
        installed.mkdir()
        self.assertEqual(inject_cython_includes('cbase', env=alias, editable=False), INJECTED)
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))
        self.assertEqual(Path(os.path.realpath(self.link)), installed.resolve())

    def test_13_explicit_site_packages(self) -> None:
        """site_packages= names the target without an environment root."""
        (self.site_packages / 'cbase').mkdir()
        status = inject_cython_includes('cbase', site_packages=self.site_packages, editable=False)
        self.assertEqual(status, INJECTED)
        self.assertEqual(os.readlink(self.link), os.path.join('..', '..', 'cbase'))

    def test_14_missing_package_without_source_skips(self) -> None:
        """A standalone call cannot link a package that is not installed."""
        self.assertEqual(self.inject(package='cbase', editable=False), SKIPPED_NO_PACKAGE)

    def test_15_env_and_site_packages_conflict(self) -> None:
        """env and site_packages are mutually exclusive."""
        with self.assertRaises(ValueError):
            inject_cython_includes('cbase', env=self.venv, site_packages=self.site_packages)

    def test_16_missing_environment(self) -> None:
        """No environment at all reports skipped-no-environment."""
        self.assertEqual(
            inject_cython_includes('cbase', env=self.root / 'missing', editable=False),
            SKIPPED_NO_ENVIRONMENT,
        )

    def test_17_explicit_includes_dir(self) -> None:
        """includes_dir= targets a Cython Includes directory directly."""
        includes = self.root / 'custom' / 'Cython' / 'Includes'
        includes.mkdir(parents=True)
        status = inject_cython_includes(
            'cbase', source=self.package_source, editable=True, includes_dir=includes
        )
        self.assertEqual(status, INJECTED)
        self.assertEqual(Path(os.path.realpath(includes / 'cbase')), self.package_source.resolve())

    def test_18_includes_dir_is_mutually_exclusive(self) -> None:
        """env, site_packages and includes_dir select one target only."""
        with self.assertRaises(ValueError):
            inject_cython_includes('cbase', env=self.venv, includes_dir=self.includes)


class TestStatusAndUninject(_FakeEnv):
    """Contract: status is observable and uninject removes only symlinks."""

    def test_00_status_transitions(self) -> None:
        """not-injected -> injected -> not-injected."""
        self.assertEqual(cython_injection_status('cbase', env=self.venv), NOT_INJECTED)
        (self.site_packages / 'cbase').mkdir()
        self.assertEqual(self.inject(package='cbase', editable=False), INJECTED)
        self.assertEqual(cython_injection_status('cbase', env=self.venv), INJECTED)
        self.assertEqual(uninject_cython_includes('cbase', env=self.venv), UNINJECTED)
        self.assertEqual(cython_injection_status('cbase', env=self.venv), NOT_INJECTED)

    def test_01_uninject_absent(self) -> None:
        """Removing an absent entry is a no-op."""
        self.assertEqual(uninject_cython_includes('cbase', env=self.venv), NOT_INJECTED)

    def test_02_uninject_leaves_real_directory(self) -> None:
        """A real directory is a conflict and survives uninject."""
        self.link.mkdir()
        (self.link / 'keep.pxd').write_text('')
        self.assertEqual(uninject_cython_includes('cbase', env=self.venv), CONFLICT)
        self.assertTrue((self.link / 'keep.pxd').is_file())

    def test_03_status_reports_conflict(self) -> None:
        """A real directory at the link path reports conflict."""
        self.link.mkdir()
        self.assertEqual(cython_injection_status('cbase', env=self.venv), CONFLICT)

    def test_04_status_skips_without_cython(self) -> None:
        """Status reports a missing Cython installation."""
        venv = self.root / 'bare-venv'
        (venv / 'lib' / 'python3.13' / 'site-packages').mkdir(parents=True)
        self.assertEqual(cython_injection_status('cbase', env=venv), SKIPPED_NO_CYTHON)

    def test_05_path_helper(self) -> None:
        """The path helper names the entry without creating it."""
        self.assertEqual(cython_injection_path('cbase', env=self.venv), self.link)
        self.assertEqual(cython_injection_path('cbase', env=self.venv, name='alias'), self.includes / 'alias')
        self.assertIsNone(cython_injection_path('cbase', env=self.root / 'missing'))


if __name__ == '__main__':
    unittest.main()
