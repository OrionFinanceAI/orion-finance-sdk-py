"""Tests for the main entry point."""

import runpy
from unittest.mock import patch


def test_main_execution():
    """Test that the main module can be executed."""
    # This covers the import line
    import orion_finance_sdk_py.__main__  # noqa: F401


def test_main_block():
    """Test the if __name__ == '__main__' block logic."""
    # We use runpy to execute the module as if it were a script
    with patch("orion_finance_sdk_py.cli.app") as mock_app:
        runpy.run_module("orion_finance_sdk_py.__main__", run_name="__main__")
        mock_app.assert_called_once()
