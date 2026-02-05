"""Tests for CLI."""

import os
from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.cli import app
from orion_finance_sdk_py.types import ZERO_ADDRESS
from typer.testing import CliRunner

# Initialize CliRunner
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
            "--strategist-address",
            "0xStrategist",
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
        strategist_address="0xStrategist",
    )


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
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
        app,
        ["submit-order", "--order-intent-path", str(order_file)],
        env={"ORION_VAULT_ADDRESS": "0xTransVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Order intent submitted successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_update_strategist(mock_ensure, MockConfig, MockVault):
    """Test update strategist."""
    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = ["0xVault"]

    mock_vault = MockVault.return_value
    mock_vault.update_strategist.return_value = MagicMock(decoded_logs=[])

    result = runner.invoke(
        app,
        ["update-strategist", "--new-strategist-address", "0xNewStrategist"],
        env={"ORION_VAULT_ADDRESS": "0xVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Strategist address updated successfully" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_update_fee_model(mock_ensure, MockConfig, MockVault):
    """Test update fee model."""
    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = ["0xVault"]

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
        env={"ORION_VAULT_ADDRESS": "0xVault", "CHAIN_ID": "11155111"},
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
            "--strategist-address",
            "0xStrategist",
        ],
    )

    assert result.exit_code == 0
    assert "Could not extract vault address" in result.stdout


@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_submit_order_unknown_vault(mock_ensure_env, MockOrionConfig, tmp_path):
    """Test submit-order with unknown vault address."""
    mock_config = MockOrionConfig.return_value
    mock_config.orion_transparent_vaults = ["0xTrans"]

    # Create dummy order file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xToken": 1}')

    result = runner.invoke(
        app,
        ["submit-order", "--order-intent-path", str(order_file)],
        env={"ORION_VAULT_ADDRESS": "0xUnknown", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code != 0
    assert "Vault address 0xUnknown not in OrionConfig contract." in str(
        result.exception
    )


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_get_pending_fees(mock_ensure, MockConfig, MockVault):
    """Test get-pending-fees command."""
    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = ["0xVault"]

    mock_vault = MockVault.return_value
    mock_vault.pending_vault_fees = 12345

    result = runner.invoke(
        app,
        ["get-pending-fees"],
        env={"ORION_VAULT_ADDRESS": "0xVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Pending Vault Fees: 12345" in result.stdout


def test_entry_point():
    """Test the CLI entry point function."""
    from orion_finance_sdk_py.cli import entry_point

    with patch("orion_finance_sdk_py.cli.app") as mock_app:
        entry_point()
        mock_app.assert_called_once()


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_claim_fees_logic(mock_ensure, MockConfig, MockVault):
    """Test claim fees logic function directly."""
    from orion_finance_sdk_py.cli import _claim_fees_logic

    mock_config = MockConfig.return_value
    mock_config.orion_transparent_vaults = ["0xVault"]

    mock_vault = MockVault.return_value
    mock_vault.transfer_manager_fees.return_value = MagicMock(decoded_logs=[])

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": "0xVault"}):
        _claim_fees_logic(100)

    mock_vault.transfer_manager_fees.assert_called_with(100)


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_update_dac_logic(mock_ensure, MockVault):
    """Test update DAC logic function directly."""
    from orion_finance_sdk_py.cli import _update_deposit_access_control_logic

    mock_vault = MockVault.return_value
    mock_vault.set_deposit_access_control.return_value = MagicMock(decoded_logs=[])

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": "0xVault"}):
        # We need to mock OrionConfig for the vault type check in logic
        with patch("orion_finance_sdk_py.cli.OrionConfig") as MockConfig:
            mock_config = MockConfig.return_value
            mock_config.orion_transparent_vaults = ["0xVault"]

            _update_deposit_access_control_logic("0xNewDAC")

    mock_vault.set_deposit_access_control.assert_called_with("0xNewDAC")


@patch("orion_finance_sdk_py.cli.interactive_menu")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_no_args(mock_ensure, mock_menu):
    """Test CLI without arguments triggers interactive menu."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    mock_ensure.assert_called_once()
    mock_menu.assert_called_once()
