"""Configuration file for the Sphinx documentation builder."""

import os
import sys
from datetime import date

# -- Path setup --------------------------------------------------------------
sys.path.insert(0, os.path.abspath("../python"))

# -- Project information -----------------------------------------------------
project = "Orion Finance SDK"
copyright = f"{date.today().year}, Orion Finance"
author = "Orion Finance"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_autodoc_typehints",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "logo": {
        "image_light": "https://docs.orionfinance.ai/img/Orion_Logo_blue_horizontal.svg",
        "image_dark": "https://docs.orionfinance.ai/img/Orion_Logo_white_horizontal.svg",
        "alt_text": "Orion Finance SDK",
    },
    "github_url": "https://github.com/OrionFinanceAI/orion-finance-sdk-py",
    "show_prev_next": False,
    "navbar_align": "right",
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "secondary_sidebar_items": ["page-toc"],
}

# -- Autodoc configuration ---------------------------------------------------
autodoc_typehints = "description"
autoclass_content = "both"  # Include __init__ docstring
