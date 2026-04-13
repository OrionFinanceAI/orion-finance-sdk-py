"""Configuration file for the Sphinx documentation builder."""

import os
import sys
from datetime import date

# -- Path setup --------------------------------------------------------------
sys.path.insert(0, os.path.abspath("../python"))

# -- Project information -----------------------------------------------------
project = "Orion | SDK"
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
    "sphinx_llms_txt",
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
html_favicon = "_static/favicon.ico"
pygments_style = "friendly"
html_title = "Orion | SDK"
html_short_title = "Orion | SDK"

html_theme_options = {
    "logo": {
        "image_light": "https://docs.orionfinance.ai/img/Orion_Logo_blue_horizontal.svg",
        "image_dark": "https://docs.orionfinance.ai/img/Orion_Logo_blue_horizontal.svg",
        "alt_text": "Orion | SDK",
    },
    "github_url": "https://github.com/OrionFinanceAI/orion-finance-sdk-py",
    "show_prev_next": False,
    "navbar_align": "right",
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "secondary_sidebar_items": ["page-toc"],
}


def setup(app):
    """Add custom CSS and JS files."""
    app.add_css_file("custom.css")
    app.add_js_file("force_light.js")


# -- Autodoc configuration ---------------------------------------------------
autodoc_typehints = "description"
autoclass_content = "both"  # Include __init__ docstring

# -- sphinx-llms-txt: single-file docs for LLMs (llms.txt, llms-full.txt) ---
# See https://sphinx-llms-txt.readthedocs.io/
#
# By default, llms-full.txt concatenates *source* .md/.rst — not rendered HTML. So
# docs/api.md appears as raw `.. autoclass::` directives (useless for LLMs) even
# though the HTML site shows full autodoc. We exclude `api` from the merge and append
# the SDK Python sources instead (`llms_txt_code_files`), which include docstrings and
# signatures in full.
# Outputs are written to _build/html/ after the HTML build.
llms_txt_title = "Orion Finance SDK"
llms_txt_summary = (
    "Python SDK for the Orion Finance protocol: deploy vaults, submit order intents, "
    "manage fees and strategist, and interact with OrionConfig and vault contracts."
)
llms_txt_exclude = ["api"]
llms_txt_code_files = [
    "+:../python/orion_finance_sdk_py/**/*.py",
    "-:../python/orion_finance_sdk_py/**/__pycache__/**",
]
