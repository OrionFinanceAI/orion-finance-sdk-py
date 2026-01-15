"""Tests for CLI."""

import os
from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.cli import app
from orion_finance_sdk_py.types import ZERO_ADDRESS
from typer.testing import CliRunner

runner = CliRunner()


@patch("orion_finance_sdk_py.cli.VaultFactory")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_deploy_vault(mock_ensure_env, MockVaultFactory):
    """Test deploying a vault."""
    mock_factory = MockVaultFactory.return_value
    mock_factory.create_orion_vault.return_value = MagicMock(
        decoded_logs=[{"event": "OrionVaultCreated", "args": {"vault": "0xVault"}}]
    )
    mock_factory.get_vault_address_from_result.return_value = "0xVault"

    result = runner.invoke(
        app,
        [
            "deploy-vault",
            "--vault-type",
            "transparent",
            "--name",
            "Test Vault",
            "--symbol",
            "TEST",
            "--fee-type",
            "absolute",
            "--performance-fee",
            "10",
            "--management-fee",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "Vault deployment transaction completed" in result.stdout
    assert "ORION_VAULT_ADDRESS=0xVault" in result.stdout

    mock_factory.create_orion_vault.assert_called_with(
        name="Test Vault",
        symbol="TEST",
        fee_type=0,
        performance_fee=1000,
        management_fee=100,
        deposit_access_control=ZERO_ADDRESS,
    )


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.contracts.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
@patch.dict("os.environ", {"ORION_VAULT_ADDRESS": "0xTransVault"})
def test_submit_order_transparent(
    mock_validate, mock_ensure, MockConfig, MockVault, tmp_path
):
    """Test submitting transparent order."""
    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = ["0xTransVault"]

    mock_vault = MockVault.return_value
    mock_vault.submit_order_intent.return_value = MagicMock(decoded_logs=[])

    # Create temp file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xA": 1.0}')

    result = runner.invoke(
        app, ["submit-order", "--order-intent-path", str(order_file)]
    )

    assert result.exit_code == 0
    assert "Order intent submitted successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionEncryptedVault")
@patch("orion_finance_sdk_py.contracts.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
@patch("orion_finance_sdk_py.cli.encrypt_order_intent")
@patch.dict("os.environ", {"ORION_VAULT_ADDRESS": "0xEncVault"})
def test_submit_order_encrypted(
    mock_encrypt, mock_validate, mock_ensure, MockConfig, MockVault, tmp_path
):
    """Test submitting encrypted order."""
    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = []
    mock_config.orion_encrypted_vaults = ["0xEncVault"]

    mock_encrypt.return_value = ({"0xA": b"enc"}, "proof")

    mock_vault = MockVault.return_value
    mock_vault.submit_order_intent.return_value = MagicMock(decoded_logs=[])

    # Create temp file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xA": 1.0}')

    result = runner.invoke(
        app, ["submit-order", "--order-intent-path", str(order_file)]
    )

    assert result.exit_code == 0
    assert "Order intent submitted successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch.dict("os.environ", {"ORION_VAULT_ADDRESS": "0xVault"})
def test_update_strategist(mock_ensure, MockVault):
    """Test update strategist."""
    mock_vault = MockVault.return_value
    mock_vault.update_strategist.return_value = MagicMock(decoded_logs=[])

    result = runner.invoke(
        app, ["update-strategist", "--new-strategist-address", "0xNewStrategist"]
    )

    assert result.exit_code == 0
    assert "Strategist address updated successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch.dict("os.environ", {"ORION_VAULT_ADDRESS": "0xVault"})
def test_update_fee_model(mock_ensure, MockVault):
    """Test update fee model."""
    mock_vault = MockVault.return_value
    mock_vault.update_fee_model.return_value = MagicMock(decoded_logs=[])

    result = runner.invoke(
        app,
        [
            "update-fee-model",
            "--fee-type",
            "absolute",
            "--performance-fee",
            "10",
            "--management-fee",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "Fee model updated successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.VaultFactory")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_deploy_vault_no_address(mock_ensure_env, MockVaultFactory):
    """Test deploy-vault command when address extraction fails."""
    mock_factory = MockVaultFactory.return_value
    mock_factory.create_orion_vault.return_value = MagicMock(
        tx_hash="0x123", decoded_logs=[]
    )
    mock_factory.get_vault_address_from_result.return_value = None

    result = runner.invoke(
        app,
        [
            "deploy-vault",
            "--vault-type",
            "transparent",
            "--name",
            "Test Vault",
            "--symbol",
            "TV",
            "--fee-type",
            "absolute",
            "--performance-fee",
            "10",
            "--management-fee",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "Could not extract vault address" in result.stdout


@patch("orion_finance_sdk_py.contracts.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_submit_order_unknown_vault(mock_ensure_env, MockOrionConfig, tmp_path):
    """Test submit-order with unknown vault address."""
    mock_config = MockOrionConfig.return_value
    mock_config.orion_transparent_vaults = ["0xTrans"]
    mock_config.orion_encrypted_vaults = ["0xEnc"]

    # Create dummy order file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xToken": 1}')

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": "0xUnknown"}):
        result = runner.invoke(
            app, ["submit-order", "--order-intent-path", str(order_file)]
        )

    assert result.exit_code == 1
    assert "Vault address 0xUnknown not in OrionConfig" in str(result.exception)


def test_entry_point():
    """Test the CLI entry point function."""
    from orion_finance_sdk_py.cli import entry_point

    with patch("orion_finance_sdk_py.cli.app") as mock_app:
        entry_point()
        mock_app.assert_called_once()
