"""Tests for the utility functions."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.types import ZERO_ADDRESS
from orion_finance_sdk_py.utils import (
    checksum_address,
    ensure_env_file,
    format_transaction_logs,
    round_with_fixed_sum,
    to_base_units,
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
    assert "STRATEGIST_PRIVATE_KEY=" in content
    assert "LP_PRIVATE_KEY=" in content


def test_ensure_env_file_exists(tmp_path):
    """Test that existing .env file is not overwritten."""
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_CONTENT=1")

    ensure_env_file(env_file)

    assert env_file.read_text() == "EXISTING_CONTENT=1"


def test_validate_var():
    """Test environment variable validation."""
    # Should raise ValueError if invalid
    with pytest.raises(ValueError, match="Error"):
        validate_var(None, "Error")

    with pytest.raises(ValueError, match="Error"):
        validate_var(ZERO_ADDRESS, "Error")

    # Should not raise
    validate_var("0x123", "Error")


def test_checksum_address_lower_and_mixed_case():
    """Lowercase and already-checksummed addresses normalize to EIP-55."""
    lower = "0x6121eaa1d94a519653721904ceab48edd98f2c3a"
    checksummed = "0x6121Eaa1D94A519653721904CEAb48eDD98f2c3a"
    assert checksum_address(lower) == checksummed
    assert checksum_address(checksummed) == checksummed
    assert checksum_address(f"  {lower}  ") == checksummed
    assert checksum_address(ZERO_ADDRESS) == ZERO_ADDRESS


def test_checksum_address_invalid_raises():
    """Non-address strings fail after checksum attempt."""
    with pytest.raises(ValueError, match="Invalid Ethereum address"):
        checksum_address("notanaddr")
    with pytest.raises(ValueError, match="Invalid Ethereum address"):
        checksum_address("0x123")


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


def test_to_base_units():
    """Human amounts convert to onchain units using token decimals."""
    assert to_base_units("1", 6) == 1_000_000
    assert to_base_units("1.5", 6) == 1_500_000
    assert to_base_units("0.000001", 6) == 1
    assert to_base_units(Decimal("100.5"), 6) == 100_500_000
    assert to_base_units("1", 18) == 10**18

    with pytest.raises(ValueError, match="more than 6 decimal places"):
        to_base_units("1.1234567", 6)
    with pytest.raises(ValueError, match="must be positive"):
        to_base_units("0", 6)
    with pytest.raises(ValueError, match="must be positive"):
        to_base_units("-1", 6)
    with pytest.raises(ValueError, match="Invalid amount"):
        to_base_units("abc", 6)
    with pytest.raises(ValueError, match="non-negative"):
        to_base_units("1", -1)


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
    token_a = "0x1111111111111111111111111111111111111111"
    token_b = "0x2222222222222222222222222222222222222222"

    # Setup mock
    mock_config = MockOrionConfig.return_value
    mock_config.is_whitelisted.return_value = True
    mock_config.strategist_intent_decimals = 9

    order = {token_a: 0.5, token_b: 0.5}

    # Normal case
    result = validate_order(order)
    assert token_a in result
    assert result[token_a] == 500000000

    # Not whitelisted
    mock_config.is_whitelisted.side_effect = lambda x: x == token_a
    with pytest.raises(ValueError, match="not whitelisted"):
        validate_order({token_b: 1.0})

    mock_config.is_whitelisted.return_value = True
    mock_config.is_whitelisted.side_effect = None

    # Negative weights
    with pytest.raises(ValueError, match="must be positive"):
        validate_order({token_a: -0.1, token_b: 1.1})

    # Sum not 1
    with pytest.raises(ValueError, match="sum of amounts is not 1"):
        validate_order({token_a: 0.5, token_b: 0.4})


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
    assert "Transaction completed successfully!" in captured.err
    assert "sepolia.etherscan.io/tx/0xabc" in captured.err
    assert "TestEvent" not in captured.err
    assert "✅" not in captured.err
