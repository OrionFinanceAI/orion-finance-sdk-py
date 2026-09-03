"""Tests for CLI."""

import os
from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.cli import app
from orion_finance_sdk_py.types import ZERO_ADDRESS
from typer.testing import CliRunner

# Initialize CliRunner
runner = CliRunner()


def _cli_output(result) -> str:
    """Combine stdout and stderr (Rich console writes to stderr)."""
    return result.stdout + result.stderr


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
    out = _cli_output(result)
    assert "Vault deployment transaction completed" in out
    assert "ORION_VAULT_ADDRESS" in out
    assert "0xVault" in out

    mock_factory.create_orion_vault.assert_called_with(
        name="Test Vault",
        symbol="TEST",
        fee_type=0,
        performance_fee=1000,
        management_fee=100,
        deposit_access_control=ZERO_ADDRESS,
        holder_access_control=ZERO_ADDRESS,
        transfer_access_control=ZERO_ADDRESS,
        strategist_address="0xStrategist",
    )
    MockVaultFactory.assert_called_with(vault_type="transparent")


@patch("orion_finance_sdk_py.cli.VaultFactory")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_deploy_vault_encrypted(mock_ensure_env, MockVaultFactory):
    """Test deploying an encrypted vault."""
    mock_factory = MockVaultFactory.return_value
    mock_factory.create_orion_vault.return_value = MagicMock(decoded_logs=[])
    mock_factory.get_vault_address_from_result.return_value = "0xEncVault"

    result = runner.invoke(
        app,
        [
            "deploy-vault",
            "--name",
            "Private Vault",
            "--symbol",
            "PRIV",
            "--fee-type",
            "absolute",
            "--performance-fee",
            "10",
            "--management-fee",
            "1",
            "--strategist-address",
            "0xStrategist",
            "--vault-type",
            "encrypted",
        ],
    )

    assert result.exit_code == 0
    MockVaultFactory.assert_called_with(vault_type="encrypted")
    out = _cli_output(result)
    assert "ORION_VAULT_ADDRESS" in out
    assert "0xEncVault" in out


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
def test_submit_intent_transparent(
    mock_validate, mock_ensure, MockConfig, MockVault, tmp_path
):
    """Test submitting transparent intent."""
    mock_config = MockConfig.return_value
    mock_config.is_encrypted_vault.return_value = False
    mock_config.orion_transparent_vaults = ["0xTransVault"]

    mock_vault = MockVault.return_value
    mock_vault.submit_order_intent.return_value = MagicMock(decoded_logs=[])

    # Create temp file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xA": 1.0}')

    result = runner.invoke(
        app,
        ["submit-intent", "--intent-path", str(order_file)],
        env={"ORION_VAULT_ADDRESS": "0xTransVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Intent submitted successfully" in _cli_output(result)


@patch("orion_finance_sdk_py.cli.OrionEncryptedVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
def test_submit_intent_encrypted(
    mock_validate, mock_ensure, MockConfig, MockVault, tmp_path
):
    """Encrypted vault submit routes to OrionEncryptedVault."""
    mock_config = MockConfig.return_value
    mock_config.is_encrypted_vault.return_value = True

    mock_validate.return_value = {"0xA": 1000}
    mock_vault = MockVault.return_value
    mock_vault.submit_order_intent.return_value = MagicMock(decoded_logs=[])

    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xA": 1.0}')

    result = runner.invoke(
        app,
        ["submit-intent", "--intent-path", str(order_file)],
        env={"ORION_VAULT_ADDRESS": "0xEncVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Intent submitted successfully" in _cli_output(result)
    mock_vault.submit_order_intent.assert_called_once_with(order_intent={"0xA": 1000})


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
@patch("orion_finance_sdk_py.cli.validate_order")
def test_submit_intent_inline_json(mock_validate, mock_ensure, MockConfig, MockVault):
    """Inline JSON object (no file) for intent."""
    mock_config = MockConfig.return_value
    mock_config.is_encrypted_vault.return_value = False
    mock_config.orion_transparent_vaults = ["0xTransVault"]

    mock_vault = MockVault.return_value
    mock_vault.submit_order_intent.return_value = MagicMock(decoded_logs=[])

    result = runner.invoke(
        app,
        ["submit-intent", "--intent", '{"0xA": 1.0}'],
        env={"ORION_VAULT_ADDRESS": "0xTransVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Intent submitted successfully" in _cli_output(result)


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_update_strategist(mock_ensure, MockConfig, MockVault):
    """Test update strategist."""
    mock_config = MockConfig.return_value
    mock_config.is_encrypted_vault.return_value = False
    mock_config.orion_transparent_vaults = ["0xVault"]

    mock_vault = MockVault.return_value
    mock_vault.update_strategist.return_value = MagicMock(decoded_logs=[])

    result = runner.invoke(
        app,
        ["update-strategist", "--new-strategist-address", "0xNewStrategist"],
        env={"ORION_VAULT_ADDRESS": "0xVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    assert "Strategist address updated successfully" in _cli_output(result)


@patch("orion_finance_sdk_py.cli.OrionTransparentVault")
@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_update_fee_model(mock_ensure, MockConfig, MockVault):
    """Test update fee model."""
    mock_config = MockConfig.return_value
    mock_config.is_encrypted_vault.return_value = False
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
    assert "Fee model updated successfully" in _cli_output(result)


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
    assert "Could not extract vault address" in _cli_output(result)


@patch("orion_finance_sdk_py.cli.OrionConfig")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_submit_intent_unknown_vault(mock_ensure_env, MockOrionConfig, tmp_path):
    """Test submit-intent with unknown vault address."""
    mock_config = MockOrionConfig.return_value
    mock_config.is_encrypted_vault.return_value = False
    mock_config.orion_transparent_vaults = ["0xTrans"]

    # Create dummy order file
    order_file = tmp_path / "order.json"
    order_file.write_text('{"0xToken": 1}')

    result = runner.invoke(
        app,
        ["submit-intent", "--intent-path", str(order_file)],
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
    mock_config.is_encrypted_vault.return_value = False
    mock_config.orion_transparent_vaults = ["0xVault"]

    mock_vault = MockVault.return_value
    mock_vault.pending_vault_fees = 12345

    result = runner.invoke(
        app,
        ["get-pending-fees"],
        env={"ORION_VAULT_ADDRESS": "0xVault", "CHAIN_ID": "11155111"},
    )

    assert result.exit_code == 0
    combined = _cli_output(result)
    assert "12345" in combined
    assert "Pending vault fees" in combined


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
    mock_config.is_encrypted_vault.return_value = False
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
            mock_config.is_encrypted_vault.return_value = False
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


@patch("orion_finance_sdk_py.cli.build_asset_address_map")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_list_asset_address_map(mock_ensure, mock_build_map):
    """Test list-asset-address-map prints testnet → mainnet rows."""
    twin = "0x1111111111111111111111111111111111111111"
    mainnet = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    mock_build_map.return_value = {twin: mainnet}

    result = runner.invoke(app, ["list-asset-address-map"])

    assert result.exit_code == 0
    combined = _cli_output(result)
    assert twin in combined
    assert mainnet in combined
    assert "Total: 1 twin assets" in combined
    mock_build_map.assert_called_once()


@patch("orion_finance_sdk_py.cli._underlying_token_meta", return_value=("USDC", 6))
@patch("orion_finance_sdk_py.cli._request_deposit_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_request_deposit(mock_ensure, mock_logic, _mock_meta):
    result = runner.invoke(app, ["request-deposit", "--assets", "1.5"])
    assert result.exit_code == 0
    mock_logic.assert_called_once_with(1_500_000)


@patch("orion_finance_sdk_py.cli._remove_vault_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_remove_vault(mock_ensure, mock_logic):
    result = runner.invoke(app, ["remove-vault"])
    assert result.exit_code == 0
    mock_logic.assert_called_once()


@patch("orion_finance_sdk_py.cli._underlying_token_meta", return_value=("USDC", 6))
@patch("orion_finance_sdk_py.cli._cancel_deposit_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_cancel_deposit_request(mock_ensure, mock_logic, _mock_meta):
    result = runner.invoke(app, ["cancel-deposit-request", "--amount", "50"])
    assert result.exit_code == 0
    mock_logic.assert_called_once_with(50_000_000)


@patch("orion_finance_sdk_py.cli._request_redeem_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_request_redeem(mock_ensure, mock_logic):
    result = runner.invoke(app, ["request-redeem", "--shares", "25"])
    assert result.exit_code == 0
    mock_logic.assert_called_once_with(25)


@patch("orion_finance_sdk_py.cli._cancel_redeem_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_cancel_redeem_request(mock_ensure, mock_logic):
    result = runner.invoke(app, ["cancel-redeem-request", "--shares", "12"])
    assert result.exit_code == 0
    mock_logic.assert_called_once_with(12)


@patch("orion_finance_sdk_py.cli._redeem_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_redeem(mock_ensure, mock_logic):
    result = runner.invoke(
        app,
        [
            "redeem",
            "--shares",
            "8",
            "--receiver",
            "0xReceiver",
            "--owner",
            "0xOwner",
        ],
    )
    assert result.exit_code == 0
    mock_logic.assert_called_once_with(8, "0xReceiver", "0xOwner")


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.lp.request_deposit")
def test_request_deposit_logic_wires_lp(mock_lp, mock_fmt):
    from orion_finance_sdk_py.cli import _request_deposit_logic

    mock_lp.return_value = MagicMock()
    _request_deposit_logic(99)
    mock_lp.assert_called_once_with(99)
    mock_fmt.assert_called_once()


@patch("orion_finance_sdk_py.cli.rpc_status")
@patch("orion_finance_sdk_py.cli.erc20_decimals", return_value=6)
@patch("orion_finance_sdk_py.cli.erc20_symbol", return_value="USDC")
@patch("orion_finance_sdk_py.cli.OrionConfig")
def test_underlying_token_meta(MockConfig, mock_symbol, mock_decimals, mock_status):
    from orion_finance_sdk_py.cli import _underlying_token_meta

    mock_status.return_value.__enter__ = MagicMock(return_value=None)
    mock_status.return_value.__exit__ = MagicMock(return_value=False)
    config = MockConfig.return_value
    config.underlying_asset = "0xA"
    config.w3 = MagicMock()
    assert _underlying_token_meta() == ("USDC", 6)


@patch("orion_finance_sdk_py.cli.rpc_status")
@patch("orion_finance_sdk_py.cli.erc20_decimals", return_value=6)
@patch("orion_finance_sdk_py.cli.erc20_symbol", side_effect=RuntimeError("no symbol"))
@patch("orion_finance_sdk_py.cli.OrionConfig")
def test_underlying_token_meta_symbol_fallback(
    MockConfig, _mock_symbol, mock_decimals, mock_status
):
    from orion_finance_sdk_py.cli import _underlying_token_meta

    mock_status.return_value.__enter__ = MagicMock(return_value=None)
    mock_status.return_value.__exit__ = MagicMock(return_value=False)
    config = MockConfig.return_value
    config.underlying_asset = "0xA"
    config.w3 = MagicMock()
    assert _underlying_token_meta() == ("tokens", 6)


@patch("orion_finance_sdk_py.cli._underlying_token_meta", return_value=("USDC", 6))
def test_human_underlying_to_base(mock_meta):
    from orion_finance_sdk_py.cli import _human_underlying_to_base

    assert _human_underlying_to_base("1.5") == 1_500_000
    mock_meta.assert_called_once()


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.lp.cancel_deposit_request")
def test_cancel_deposit_logic_wires_lp(mock_lp, mock_fmt):
    from orion_finance_sdk_py.cli import _cancel_deposit_logic

    mock_lp.return_value = MagicMock()
    _cancel_deposit_logic(5)
    mock_lp.assert_called_once_with(5)


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.lp.request_redeem")
def test_request_redeem_logic_wires_lp(mock_lp, mock_fmt):
    from orion_finance_sdk_py.cli import _request_redeem_logic

    mock_lp.return_value = MagicMock()
    _request_redeem_logic(7)
    mock_lp.assert_called_once_with(7)


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.lp.cancel_redeem_request")
def test_cancel_redeem_logic_wires_lp(mock_lp, mock_fmt):
    from orion_finance_sdk_py.cli import _cancel_redeem_logic

    mock_lp.return_value = MagicMock()
    _cancel_redeem_logic(3)
    mock_lp.assert_called_once_with(3)


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.lp.redeem")
def test_redeem_logic_wires_lp(mock_lp, mock_fmt):
    from orion_finance_sdk_py.cli import _redeem_logic

    mock_lp.return_value = MagicMock()
    _redeem_logic(1, "0xR", "0xO")
    mock_lp.assert_called_once_with(1, "0xR", "0xO")


@patch("orion_finance_sdk_py.cli.format_transaction_logs")
@patch("orion_finance_sdk_py.manager.remove_orion_vault")
def test_remove_vault_logic_wires_manager(mock_mgr, mock_fmt):
    from orion_finance_sdk_py.cli import _remove_vault_logic

    mock_mgr.return_value = MagicMock()
    _remove_vault_logic()
    mock_mgr.assert_called_once_with()
    mock_fmt.assert_called_once()


def test_validate_int_input():
    from orion_finance_sdk_py.cli import validate_int_input

    assert validate_int_input("5") is True
    assert validate_int_input("0") == "Amount must be positive"
    assert validate_int_input("abc") == "Please enter a valid integer"


def test_validate_decimal_input():
    from orion_finance_sdk_py.cli import _validate_human_amount, validate_decimal_input

    assert validate_decimal_input("1.5") is True
    assert validate_decimal_input("0") == "Amount must be positive"
    assert validate_decimal_input("abc") == "Invalid amount: abc"

    validate = _validate_human_amount(6)
    assert validate("1.5") is True
    assert "more than 6 decimal places" in validate("1.1234567")


@patch("orion_finance_sdk_py.cli.OrionConfig")
def test_list_whitelisted_assets_logic(MockConfig, capsys):
    from orion_finance_sdk_py.cli import _list_whitelisted_assets_logic

    config = MockConfig.return_value
    config.whitelisted_assets = ["0xA", "0xB"]
    config.whitelisted_asset_names = ["AAA", "BBB"]
    _list_whitelisted_assets_logic()
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "AAA" in out and "0xA" in out
    assert "Total: 2" in out


@patch("orion_finance_sdk_py.cli.OrionConfig")
def test_list_whitelisted_assets_logic_names_fallback(MockConfig, capsys):
    from orion_finance_sdk_py.cli import _list_whitelisted_assets_logic

    config = MockConfig.return_value
    config.whitelisted_assets = ["0xA"]
    type(config).whitelisted_asset_names = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("no names"))
    )
    _list_whitelisted_assets_logic()
    captured = capsys.readouterr()
    assert "Unknown" in captured.out + captured.err


@patch("orion_finance_sdk_py.cli._list_whitelisted_assets_logic")
@patch("orion_finance_sdk_py.cli.ensure_env_file")
def test_cli_list_whitelisted_assets(mock_ensure, mock_logic):
    result = runner.invoke(app, ["list-whitelisted-assets"])
    assert result.exit_code == 0
    mock_logic.assert_called_once()


@patch("orion_finance_sdk_py.cli.print_error")
@patch("orion_finance_sdk_py.cli.app")
def test_entry_point_value_error(mock_app, mock_print_error):
    from orion_finance_sdk_py.cli import entry_point

    mock_app.side_effect = ValueError("boom")
    with patch("orion_finance_sdk_py.cli.sys.exit") as mock_exit:
        entry_point()
    mock_print_error.assert_called_once_with("boom")
    mock_exit.assert_called_once_with(1)
