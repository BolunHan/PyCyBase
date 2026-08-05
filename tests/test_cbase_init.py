"""Smoke test for the cbase package root.

Contract: CONFIG_VIEW is a read-only, per-submodule nested mapping;
get_include returns real resource directories and logs the build banner with
the config view rendered as nested "- key: value" bullet lines rather than
the raw dict-view repr.

Oracle: directory existence checked with os.path.isdir; the banner text is
captured from the package logger and validated line by line.
"""
import logging
import os
import unittest
from collections.abc import Mapping

import cbase


class _RecordCapture(logging.Handler):
    """Collects LogRecords emitted on the package logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestConfigView(unittest.TestCase):
    """Contract: CONFIG_VIEW nests one read-only section per submodule.

    Expected behavior:
        - top-level keys are the submodule sections;
        - every section is a mapping of scalar leaves;
        - neither the outer nor any inner mapping is mutable.
    """

    @classmethod
    def _leaf_keys(cls, config: Mapping):
        """Yield the scalar leaf keys of a (possibly nested) mapping."""
        for key, value in config.items():
            if isinstance(value, Mapping):
                yield from cls._leaf_keys(value)
            else:
                yield key

    def test_00_nested_sections(self) -> None:
        """CONFIG_VIEW has one section per submodule, leaves are scalars."""
        expected_sections = {'allocator_protocol', 'heap', 'shm', 'bytemap', 'intern_string'}
        self.assertEqual(set(cbase.CONFIG_VIEW), expected_sections)
        for section, section_view in cbase.CONFIG_VIEW.items():
            self.assertIsInstance(section_view, Mapping)
            for value in section_view.values():
                self.assertFalse(isinstance(value, Mapping), f'{section} should contain only scalar leaves')

    def test_01_readonly_every_level(self) -> None:
        """Item assignment is rejected on the outer and inner views."""
        with self.assertRaises(TypeError):
            cbase.CONFIG_VIEW['heap'] = {}
        with self.assertRaises(TypeError):
            cbase.CONFIG_VIEW['heap']['AP_HEAP_BIN_COUNT'] = 0


class TestGetInclude(unittest.TestCase):
    """Contract: cbase.get_include() returns existing include directories and
    logs a config-view banner on first call.

    Expected behavior:
        - every returned path is an existing directory;
        - repeated calls return the cached list (functools.cache);
        - the banner renders CONFIG_VIEW as nested "- key: value" bullets.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = _RecordCapture()
        cbase.LOGGER.addHandler(cls.capture)

    @classmethod
    def tearDownClass(cls) -> None:
        cbase.LOGGER.removeHandler(cls.capture)

    def test_00_returns_existing_dirs(self) -> None:
        """All returned paths exist as directories."""
        include_dirs = cbase.get_include()
        self.assertTrue(include_dirs)
        for include_dir in include_dirs:
            self.assertTrue(os.path.isdir(include_dir), f'not a directory: {include_dir}')

    def test_01_cached_result(self) -> None:
        """Repeated calls return the same cached list object."""
        self.assertIs(cbase.get_include(), cbase.get_include())

    def test_02_banner_lists_config_bullets(self) -> None:
        """The build banner renders CONFIG_VIEW as nested '- key: value' lines."""
        banner = next(
            (r.getMessage() for r in self.capture.records if 'Building with <PyCyBase>' in r.getMessage()),
            None,
        )
        self.assertIsNotNone(banner, 'build banner was not logged by get_include')
        self.assertIn('config:', banner)
        for section in cbase.CONFIG_VIEW:
            self.assertIn(f"- {section}:", banner, f'config section {section!r} missing from banner')
        for key in TestConfigView._leaf_keys(cbase.CONFIG_VIEW):
            self.assertIn(f"- {key}: ", banner, f'config key {key!r} missing from banner')
        self.assertNotIn('mappingproxy', banner)


if __name__ == '__main__':
    unittest.main()
