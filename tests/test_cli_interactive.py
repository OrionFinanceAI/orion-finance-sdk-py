"""Tests for the interactive CLI menu."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.cli import ask_or_exit, interactive_menu
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


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._deploy_vault_logic")
def test_interactive_menu_deploy_vault(mock_deploy_logic, mock_questionary, mock_input):
    """Test interactive menu Deploy Vault flow."""
    # Setup mocks for questionary sequence
    # 1. Main menu -> "Deploy Vault"
    # 2. Vault Type -> TRANSPARENT
    # 3. Name -> "Test Vault"
    # 4. Symbol -> "TV"
    # 5. Fee Type -> "absolute"
    # 6. Perf Fee -> "10"
    # 7. Mgmt Fee -> "1"
    # 8. DAC -> "0x0"
    # 9. Main menu -> "Exit"

    # We need to configure side_effect for the asks to simulate the sequence
    # Order of asks:
    # 1. select(Main Menu)
    # 2. select(Vault Type)
    # 3. text(Name)
    # 4. text(Symbol)
    # 5. select(Fee Type)
    # 6. text(Perf Fee)
    # 7. text(Mgmt Fee)
    # 8. text(DAC)
    # 9. select(Main Menu)

    # BUT questionary calls are interleaved.
    # We can mock the specific question objects returned.

    # Easier approach: Use side_effects on the question objects returned by select/text
    # But select() returns a new object each time.

    # Let's mock questionary.select and questionary.text to return Mock objects with specific ask side effects.

    # Sequence of return values for ask() calls across all widgets
    # This assumes a specific order of execution in the code
    ask_side_effect = [
        "Deploy Vault",  # Main menu
        VaultType.TRANSPARENT.value,  # Vault Type
        "Test Vault",  # Name
        "TV",  # Symbol
        "absolute",  # Fee Type
        "10",  # Perf Fee
        "1",  # Mgmt Fee
        "0x0",  # DAC
        "Exit",  # Main menu loop again
    ]

    # We need a shared iterator for the side effect
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
    assert args[1] == "Test Vault"
    assert args[2] == "TV"
    assert args[3] == 0  # absolute fee int
    assert args[4] == 1000  # 10 * 100
    assert args[5] == 100  # 1 * 100
    assert args[6] == "0x0"


@patch("builtins.input")
@patch("orion_finance_sdk_py.cli.questionary")
@patch("orion_finance_sdk_py.cli._submit_order_logic")
def test_interactive_menu_submit_order(mock_submit_logic, mock_questionary, mock_input):
    """Test interactive menu Submit Order flow."""
    # Sequence:
    # 1. Main menu -> "Submit Order"
    # 2. Path -> "order.json"
    # 3. Fuzz -> True
    # 4. Main menu -> "Exit"

    ask_side_effect = [
        "Submit Order",
        "order.json",
        True,
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    mock_questionary.select.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.path.return_value.ask.side_effect = lambda: next(iterator)
    mock_questionary.confirm.return_value.ask.side_effect = lambda: next(iterator)

    interactive_menu()

    mock_submit_logic.assert_called_once_with("order.json", True)


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
    # Sequence:
    # 1. Main menu -> "Deploy Vault"
    # 2. Vault Type -> KeyboardInterrupt (simulate Ctrl+C)
    # 3. Main menu -> "Exit"

    # We need ask() to return "Deploy Vault", then raise KeyboardInterrupt (via ask_or_exit which checks for None), then return "Exit".
    # Wait, ask_or_exit logic: if ask() returns None, it raises KeyboardInterrupt.
    # So we simulate ask() returning None.

    ask_side_effect = [
        "Deploy Vault",
        None,  # Simulates Ctrl+C inside sub-menu
        "Exit",
    ]
    iterator = iter(ask_side_effect)

    def next_answer():
        val = next(iterator)
        return val

    mock_questionary.select.return_value.ask.side_effect = next_answer
    # We need select().ask() to return None for the sub-menu call

    # However, "Deploy Vault" is a select call.
    # "Vault Type" is ALSO a select call.
    # So subsequent calls to select(...).ask() pull from the same iterator.

    interactive_menu()

    # If it finishes without raising error, it caught the KeyboardInterrupt and looped back.
    assert mock_questionary.select.call_count >= 2
