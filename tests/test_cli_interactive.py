"""Tests for the interactive CLI menu."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.cli import (
    ask_or_exit,
    interactive_menu,
    validate_name,
    validate_symbol,
)
from orion_finance_sdk_py.types import VaultType


def test_ask_or_exit_success():
    """Test ask_or_exit returns value when user answers."""
    mock_question = MagicMock()
    mock_question.ask.return_value = "answer"
    assert ask_or_exit(mock_question) == "answer"


def test_ask_or_exit_cancel():
    """Test ask_or_exit raises KeyboardInterrupt when user cancels (returns None)."""
    mock_question = MagicMock()
    mock_question.ask.return_value = None
    with pytest.raises(KeyboardInterrupt):
        ask_or_exit(mock_question)


def test_validate_name():
    """Test validate_name logic."""
    assert validate_name("Valid Name") is True
    assert validate_name("") == "Name cannot be empty"
    assert validate_name("A" * 27) == "Name too long (max 26 bytes)"
    # Multibyte char test
    assert validate_name("🚀" * 6) is True  # 6 * 4 bytes = 24 bytes
    assert validate_name("🚀" * 7) == "Name too long (max 26 bytes)"  # 28 bytes


def test_validate_symbol():
    """Test validate_symbol logic."""
    assert validate_symbol("SYM") is True
    assert validate_symbol("") == "Symbol cannot be empty"
    assert validate_symbol("SYMB1") == "Symbol too long (max 4 bytes)"
    # Multibyte char test
    assert validate_symbol("🚀") is True  # 4 bytes
    assert validate_symbol("🚀A") == "Symbol too long (max 4 bytes)"  # 5 bytes


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._deploy_vault_logic")
def test_interactive_menu_deploy_vault(mock_deploy_logic, mock_questionary, mock_input):
    """Test interactive menu Deploy Vault flow."""
    # Sequence of return values for ask() calls across all widgets
    ask_side_effect = [
        "Deploy Vault",  # Main menu
        "0xStrategist",  # Strategist Address
        "Test Vault",  # Name
        "TV",  # Symbol
        "absolute",  # Fee Type
        "",  # Perf Fee (empty -> 0.0)
        "",  # Mgmt Fee (empty -> 0.0)
        "0x0",  # DAC
        "Exit",  # Main menu loop again
    ]

    iterator = iter(ask_side_effect)

    def next_answer():
        return next(iterator)

    # Configure the mock objects returned by questionary functions
    mock_questionary.select.return_value.ask.side_effect = next_answer
    mock_questionary.text.return_value.ask.side_effect = next_answer

    interactive_menu()

    mock_deploy_logic.assert_called_once()
    args = mock_deploy_logic.call_args[0]
    assert args[0] == VaultType.TRANSPARENT.value
    assert args[1] == "0xStrategist"
    assert args[2] == "Test Vault"
    assert args[3] == "TV"
    assert args[4] == 0  # absolute fee int
    assert args[5] == 0  # 0.0 * 100
    assert args[6] == 0  # 0.0 * 100
    assert args[7] == "0x0"


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._submit_order_logic")
def test_interactive_menu_submit_order(mock_submit_logic, mock_questionary, mock_input):
    """Test interactive menu Submit Order flow."""
    # Sequence:
    # 1. Main menu -> "Submit Order"
    # 2. Path -> "order.json"
    # 3. Main menu -> "Exit"

    ask_side_effect = [
        "Submit Order",
        "order.json",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.path.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_submit_logic.assert_called_once_with("order.json")


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._update_strategist_logic")
def test_interactive_menu_update_strategist(
    mock_update_logic, mock_questionary, mock_input
):
    """Test interactive menu Update Strategist flow."""
    # Sequence:
    # 1. Main menu -> "Update Strategist"
    # 2. Address -> "0xNew"
    # 3. Main menu -> "Exit"

    ask_side_effect = [
        "Update Strategist",
        "0xNew",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.text.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_update_logic.assert_called_once_with("0xNew")


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._update_fee_model_logic")
def test_interactive_menu_update_fee_model(
    mock_fee_logic, mock_questionary, mock_input
):
    """Test interactive menu Update Fee Model flow."""
    # Sequence:
    # 1. Main menu -> "Update Fee Model"
    # 2. Fee Type -> "absolute"
    # 3. Perf Fee -> "10"
    # 4. Mgmt Fee -> "1"
    # 5. Main menu -> "Exit"

    ask_side_effect = [
        "Update Fee Model",
        "absolute",
        "10",
        "1",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.text.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_fee_logic.assert_called_once()
    args = mock_fee_logic.call_args[0]
    assert args[0] == 0  # absolute
    assert args[1] == 1000
    assert args[2] == 100


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
def test_interactive_menu_cancel(mock_questionary, mock_input):
    """Test interactive menu handles KeyboardInterrupt gracefully."""
    ask_side_effect = [
        "Deploy Vault",
        None,  # Simulates Ctrl+C inside Name prompt
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    def next_answer():
        val = next(iterator)
        return val

    mock_questionary.select.return_value.ask.side_effect = next_answer
    mock_questionary.text.return_value.ask.side_effect = next_answer

    interactive_menu()

    assert mock_questionary.select.call_count >= 2


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._update_deposit_access_control_logic")
def test_interactive_menu_update_dac(mock_dac_logic, mock_questionary, mock_input):
    """Test interactive menu Update DAC flow."""
    ask_side_effect = [
        "Update Deposit Access Control",
        "0xDAC",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.text.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_dac_logic.assert_called_once_with("0xDAC")


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._claim_fees_logic")
def test_interactive_menu_claim_fees(mock_claim_logic, mock_questionary, mock_input):
    """Test interactive menu Claim Fees flow."""
    ask_side_effect = [
        "Claim Fees",
        "100",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.text.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_claim_logic.assert_called_once_with(100)


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._get_pending_fees_logic")
def test_interactive_menu_get_pending_fees(
    mock_pending_logic, mock_questionary, mock_input
):
    """Test interactive menu Get Pending Fees flow."""
    ask_side_effect = [
        "Get Pending Fees",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_pending_logic.assert_called_once()


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._deploy_vault_logic")
def test_interactive_menu_error_handling(
    mock_deploy_logic, mock_questionary, mock_input
):
    """Test interactive menu handles errors gracefully."""
    mock_deploy_logic.side_effect = ValueError("Test Error")

    ask_side_effect = [
        "Deploy Vault",
        "0xStrategist",
        "Name",
        "Symbol",
        "absolute",
        "1",
        "1",
        "0x0",
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    def next_answer():
        return next(iterator)

    mock_questionary.select.return_value.ask.side_effect = next_answer
    mock_questionary.text.return_value.ask.side_effect = next_answer

    interactive_menu()

    # Should call deploy, raise error, catch it, wait for input, and loop back to Exit
    mock_deploy_logic.assert_called_once()
    assert mock_input.call_count >= 1  # "Press Enter to continue..."
