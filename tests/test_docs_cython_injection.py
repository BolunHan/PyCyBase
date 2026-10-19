"""Contract tests keeping the injection docs in sync with the shipped API.

Expected behavior:
    - every public callable defined by cbase.cython_injection appears in
      docs/cython_injection.rst;
    - docs/index.rst lists the page in its toctree;
    - README.md shows the downstream entry point;
    - the page parses as reStructuredText when docutils is installed.
"""
import unittest
from pathlib import Path

import cbase.cython_injection as injection

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / 'docs' / 'cython_injection.rst'
INDEX_PATH = ROOT / 'docs' / 'index.rst'
README_PATH = ROOT / 'README.md'


class TestCythonInjectionDocs(unittest.TestCase):
    """Contract: documentation matches the public module surface."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = DOC_PATH.read_text()

    def test_00_public_callables_documented(self) -> None:
        """Every public callable defined in the module is named in the docs."""
        public = sorted(
            name
            for name, obj in vars(injection).items()
            if not name.startswith('_')
            and callable(obj)
            and getattr(obj, '__module__', None) == injection.__name__
        )
        self.assertTrue(public)
        for name in public:
            self.assertIn(name, self.doc, f'{name} is missing from {DOC_PATH}')

    def test_01_required_topics_documented(self) -> None:
        """The page covers detection, link layout, idempotency and reusability."""
        for needle in (
            'Environment detection',
            '../../<package>',
            'already-injected',
            'uninject_cython_includes',
            'Windows',
            'algo_engine',
        ):
            self.assertIn(needle, self.doc, f'{needle!r} is missing from {DOC_PATH}')

    def test_02_index_toctree(self) -> None:
        """docs/index.rst references the new page."""
        self.assertIn('cython_injection', INDEX_PATH.read_text())

    def test_03_readme_reuse_example(self) -> None:
        """README shows the downstream entry point."""
        self.assertIn('inject_cython_includes', README_PATH.read_text())

    def test_04_rst_parses(self) -> None:
        """The page parses as reStructuredText.

        Sphinx registers ``autofunction``, ``autoclass`` and ``code-block``;
        plain docutils does not, so stand-ins are registered for this parse.
        """
        try:
            from docutils import nodes
            from docutils.core import publish_doctree
            from docutils.parsers.rst import Directive, directives
        except ImportError:
            self.skipTest('docutils is not installed')

        class _SphinxDirective(Directive):
            required_arguments = 1
            final_argument_whitespace = True
            has_content = True

            def run(self):
                return [nodes.literal_block('', ' '.join(self.arguments))]

        names = ('autofunction', 'autoclass', 'code-block')
        for name in names:
            directives.register_directive(name, _SphinxDirective)
        try:
            publish_doctree(self.doc, settings_overrides={'halt_level': 2, 'report_level': 2})
        finally:
            for name in names:
                directives.register_directive(name, None)


if __name__ == '__main__':
    unittest.main()
