"""Tests for console_ui presentation helpers."""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py import console_ui


@pytest.fixture
def capture_console():
    """Redirect module console to a StringIO buffer."""
    buffer = StringIO()
    test_console = console_ui.Console(file=buffer, force_terminal=True, width=120)
    with patch.object(console_ui, "console", test_console):
        yield buffer


def test_print_tx_result(capture_console):
    tx_result = MagicMock()
    tx_result.tx_hash = "a" * 62  # 0x + 62 hex chars after normalize

    console_ui.print_tx_result(tx_result, title="Intent submitted")

    out = capture_console.getvalue()
    assert "Intent submitted" in out
    assert "…" in out
    assert "sepolia.etherscan.io/tx/0x" in out
    assert "✅" not in out
    assert "🔗" not in out


def test_print_key_value(capture_console):
    console_ui.print_key_value([("ORION_VAULT_ADDRESS", "0xVault")], title="Vault address")
    out = capture_console.getvalue()
    assert "ORION_VAULT_ADDRESS" in out
    assert "0xVault" in out


def test_print_table_caption(capture_console):
    console_ui.print_table(
        ["Name", "Address"],
        [("USDC", "0xA")],
        title="Whitelisted assets",
        caption="Total: 1 whitelisted assets",
    )
    out = capture_console.getvalue()
    assert "USDC" in out
    assert "Total: 1" in out
    assert "whitelisted assets" in out


def test_rpc_status_uses_spinner():
    mock_status = MagicMock()
    mock_status.__enter__ = MagicMock(return_value=None)
    mock_status.__exit__ = MagicMock(return_value=False)
    mock_console = MagicMock()
    mock_console.status.return_value = mock_status

    with patch.object(console_ui, "console", mock_console):
        with console_ui.rpc_status("Working…"):
            pass

    mock_console.status.assert_called_once_with("Working…", spinner="dots")


def test_print_error(capture_console):
    console_ui.print_error("something failed")
    assert "Error:" in capture_console.getvalue()
    assert "something failed" in capture_console.getvalue()


def test_progress_step_noop_without_context():
    """progress_step is silent when no operation_progress is active."""
    console_ui.progress_step("Should not appear")


def test_operation_progress_steps(capture_console):
    with console_ui.operation_progress("Submit intent"):
        console_ui.progress_step("Loading intent from source")
        console_ui.progress_step("Validating tokens against whitelist")

    out = capture_console.getvalue()
    assert "Submit intent" in out
    assert "Loading intent from source" in out
    assert "Validating tokens against whitelist" in out


def test_operation_progress_non_tty_prints_lines(capture_console):
    test_console = console_ui.Console(file=capture_console, force_terminal=False, width=120)
    with patch.object(console_ui, "console", test_console):
        with console_ui.operation_progress("Deploy vault"):
            console_ui.progress_step("Verifying manager whitelist")
            console_ui.progress_step("Broadcasting createVault transaction")

    out = capture_console.getvalue()
    assert "Verifying manager whitelist" in out
    assert "Broadcasting createVault transaction" in out


def test_print_welcome(capture_console):
    console_ui.print_welcome()
    out = capture_console.getvalue()
    assert "Orion Console" in out
    assert "Orion Finance" in out
    assert "institutional capital" in out
    assert "orionfinance.ai" in out
    assert "sdk.orionfinance.ai" in out
