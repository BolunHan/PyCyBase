# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add project root to path for autodoc
sys.path.insert(0, os.path.abspath('..'))

# Import version from package
try:
    from cbase import __version__

    release = f'v{__version__}'
    version = f'v{__version__}'
except ImportError:
    release = 'unknown'
    version = 'unknown'

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'PyCyBase'
copyright = '2025–2026, Bolun Han'
author = 'Bolun Han'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Napoleon settings for Google-style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__',
}

# Don't require imports to succeed for autodoc (modules may be mocked during CI builds)
autodoc_mock_imports = []

# Silence autodoc import failures for Cython extension submodules that
# Sphinx cannot fully introspect.  The automodule directive still generates
# complete documentation for all classes and members.
suppress_warnings = ["autodoc.import_object"]

# autodoc-typehints: load type information from .pyi stub files.
# This ensures the rich Google-style docstrings and type annotations from
# the .pyi stubs are injected into the rendered API documentation.
autodoc_typehints = "both"
autodoc_typehints_format = "short"
typehints_fully_qualified = False
always_document_param_types = True

# Intersphinx mapping to link to Python stdlib docs
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
html_title = f"{project} {release}"

# Furo theme options
html_theme_options = {
    "sidebar_hide_name": False,
    "navigation_with_keys": True,
}
