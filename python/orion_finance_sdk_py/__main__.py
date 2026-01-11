"""Main entry point for the Orion Finance Python SDK."""

import sys

from .cli import ORION_BANNER, app

if __name__ == "__main__":
    print(ORION_BANNER, file=sys.stderr)
    app()
