"""Tests for the utility functions."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.utils import (
    ensure_env_file,
    format_transaction_logs,
    round_with_fixed_sum,
    validate_management_fee,
    validate_order,
    validate_performance_fee,
    validate_var,
)


def test_ensure_env_file(tmp_path):
    """Test that .env file is created if it doesn't exist."""
    env_file = tmp_path / ".env"
    assert not env_file.exists()

    # Run function
    ensure_env_file(env_file)

    assert env_file.exists()
    content = env_file.read_text()
    assert "STRATEGIST_ADDRESS=" in content
    assert "STRATEGIST_PRIVATE_KEY=" in content


def test_ensure_env_file_exists(tmp_path):
    """Test that existing .env file is not overwritten."""
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_CONTENT=1")

    ensure_env_file(env_file)

    assert env_file.read_text() == "EXISTING_CONTENT=1"


def test_validate_var():
    """Test environment variable validation."""
    # Should exit if invalid
    with pytest.raises(SystemExit):
        validate_var(None, "Error")

    with pytest.raises(SystemExit):
        validate_var("0x0000000000000000000000000000000000000000", "Error")

    # Should not raise
    validate_var("0x123", "Error")


def test_validate_performance_fee():
    """Test performance fee validation."""
    validate_performance_fee(3000)

    with pytest.raises(ValueError, match="exceeds maximum allowed value"):
        validate_performance_fee(3001)


def test_validate_management_fee():
    """Test management fee validation."""
    validate_management_fee(300)

    with pytest.raises(ValueError, match="exceeds maximum allowed value"):
        validate_management_fee(301)


def test_round_with_fixed_sum():
    """Test rounding logic."""
    values = [33.333, 33.333, 33.334]
    target_sum = 100

    rounded = round_with_fixed_sum(values, target_sum)
    assert sum(rounded) == target_sum
    assert rounded == [33, 33, 34]  # Actually depends on logic, but sum must match

    # Test with different inputs
    values = [10.1, 20.2, 30.3]
    # Sum is 60.6 -> target 61? No, logic rounds sum of inputs if not provided.
    # Default target sum: round(60.6) = 61
    rounded = round_with_fixed_sum(values)
    assert sum(rounded) == 61


@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_validate_order(MockOrionConfig):
    """Test order validation."""
    # Setup mock
    mock_config = MockOrionConfig.return_value
    mock_config.is_whitelisted.return_value = True
    mock_config.strategist_intent_decimals = 9

    order = {"0xA": 0.5, "0xB": 0.5}

    # Normal case
    result = validate_order(order)
    assert "0xA" in result
    assert result["0xA"] == 500000000

    # Not whitelisted
    mock_config.is_whitelisted.side_effect = lambda x: x == "0xA"
    with pytest.raises(ValueError, match="not whitelisted"):
        validate_order({"0xB": 1.0})

    mock_config.is_whitelisted.return_value = True
    mock_config.is_whitelisted.side_effect = None

    # Negative weights
    with pytest.raises(ValueError, match="must be positive"):
        validate_order({"0xA": -0.1, "0xB": 1.1})

    # Sum not 1
    with pytest.raises(ValueError, match="sum of amounts is not 1"):
        validate_order({"0xA": 0.5, "0xB": 0.4})

    # Fuzzing
    mock_config.whitelisted_assets = ["0xC"]
    # Should add 0xC
    result = validate_order({"0xA": 0.5, "0xB": 0.5}, fuzz=True)
    assert "0xC" in result
    assert len(result) == 3


def test_format_transaction_logs(capsys):
    """Test log formatting."""
    tx_result = MagicMock()
    tx_result.tx_hash = "abc"
    tx_result.decoded_logs = [
        {
            "event": "TestEvent",
            "args": {"key": "value"},
            "address": "0x123",
            "blockNumber": 1,
        }
    ]

    format_transaction_logs(tx_result)
    captured = capsys.readouterr()
    assert "TestEvent" in captured.out
    assert "key: value" in captured.out
    assert "https://sepolia.etherscan.io/tx/0xabc" in captured.out
