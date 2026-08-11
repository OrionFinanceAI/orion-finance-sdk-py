"""Tests for role-scoped LP / manager / strategist APIs."""

import os
from unittest.mock import MagicMock, patch

import pytest
from eth_utils import function_signature_to_4byte_selector
from orion_finance_sdk_py import lp, manager, strategist, views
from orion_finance_sdk_py.contracts import (
    OrionTransparentVault,
    SystemNotIdleError,
    TransactionResult,
)
from orion_finance_sdk_py.errors import decode_revert_data, format_revert
from orion_finance_sdk_py.events import parse_lp_events_from_receipt


@pytest.fixture
def mock_env():
    env_vars = {
        "RPC_URL": "http://localhost:8545",
        "CHAIN_ID": "11155111",
        "MANAGER_PRIVATE_KEY": "0xPrivate",
        "STRATEGIST_PRIVATE_KEY": "0xPrivate",
        "LP_PRIVATE_KEY": "0xPrivate",
        "ORION_VAULT_ADDRESS": "0xVault",
    }
    with patch.dict(os.environ, env_vars):
        yield


@patch("orion_finance_sdk_py.lp.approve")
@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_deposit_approves_then_calls(MockConfig, mock_resolve, mock_approve):
    """LP request_deposit approves underlying then requestDeposit."""
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 1
    config.underlying_asset = "0xUnderlying"
    config.is_decommissioning_vault.return_value = False
    config.is_decommissioned_vault.return_value = False

    vault = MagicMock()
    vault.contract_address = "0xVault"
    vault.w3 = MagicMock()
    vault.request_deposit.return_value = TransactionResult(
        tx_hash="0x1", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    res = lp.request_deposit(1000)

    mock_approve.assert_called_once()
    vault.request_deposit.assert_called_once_with(1000, key_env="LP_PRIVATE_KEY")
    assert res.tx_hash == "0x1"


@patch("orion_finance_sdk_py.lp.approve")
@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_redeem_approves_shares(MockConfig, mock_resolve, mock_approve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_redeem_amount = 1
    config.is_decommissioned_vault.return_value = False

    vault = MagicMock()
    vault.contract_address = "0xVault"
    vault.w3 = MagicMock()
    vault.request_redeem.return_value = TransactionResult(
        tx_hash="0x2", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    lp.request_redeem(50)

    mock_approve.assert_called_once()
    assert mock_approve.call_args.args[1] == "0xVault"
    assert mock_approve.call_args.args[2] == "0xVault"
    vault.request_redeem.assert_called_once_with(50, key_env="LP_PRIVATE_KEY")


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_deposit_rejects_when_not_idle(MockConfig, mock_resolve):
    MockConfig.return_value.is_system_idle.return_value = False
    with pytest.raises(SystemNotIdleError):
        lp.request_deposit(100)


@patch("orion_finance_sdk_py.lp.resolve_vault")
def test_lp_redeem_delegates(mock_resolve):
    vault = MagicMock()
    vault.redeem.return_value = TransactionResult(
        tx_hash="0x3", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    lp.redeem(10, "0xReceiver", "0xOwner")
    vault.redeem.assert_called_once_with(
        10, "0xReceiver", "0xOwner", key_env="LP_PRIVATE_KEY"
    )


@patch("orion_finance_sdk_py.manager.VaultFactory")
def test_manager_create_vault(MockFactory):
    factory = MockFactory.return_value
    factory.create_orion_vault.return_value = TransactionResult(
        tx_hash="0x4", receipt={"status": 1}, decoded_logs=[]
    )
    manager.create_vault(
        vault_type="encrypted",
        strategist_address="0xS",
        name="Priv",
        symbol="P",
        fee_type=0,
        performance_fee=100,
        management_fee=10,
        deposit_access_control="0x0",
    )
    MockFactory.assert_called_once_with(vault_type="encrypted")
    factory.create_orion_vault.assert_called_once()


@patch("orion_finance_sdk_py.manager.OrionConfig")
@patch("orion_finance_sdk_py.manager.resolve_vault")
def test_manager_remove_orion_vault(mock_resolve, MockConfig):
    vault = MagicMock()
    vault.contract_address = "0xVault"
    mock_resolve.return_value = vault
    MockConfig.return_value.remove_orion_vault.return_value = TransactionResult(
        tx_hash="0x5", receipt={"status": 1}, decoded_logs=[]
    )

    manager.remove_orion_vault()
    MockConfig.return_value.remove_orion_vault.assert_called_once_with("0xVault")


@patch("orion_finance_sdk_py.strategist.resolve_vault")
def test_strategist_submit_intent_routes(mock_resolve):
    vault = MagicMock()
    vault.submit_order_intent.return_value = TransactionResult(
        tx_hash="0x6", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    strategist.submit_intent({"0xA": 1000})
    vault.submit_order_intent.assert_called_once_with({"0xA": 1000})


def test_exports_exclude_admin_and_acl():
    import orion_finance_sdk_py as sdk

    assert "WhitelistAccessControl" not in sdk.__all__
    assert not hasattr(sdk, "WhitelistAccessControl")
    assert "permissionless" not in sdk.__all__
    assert not hasattr(sdk, "permissionless")
    assert "lp" in sdk.__all__
    assert "manager" in sdk.__all__


@patch("orion_finance_sdk_py.views.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.views.resolve_vault")
@patch("orion_finance_sdk_py.views.OrionConfig")
def test_views_eligibility_snapshot(MockConfig, mock_resolve, MockLO):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 1
    config.min_redeem_amount = 2
    config.is_encrypted_vault.return_value = False
    config.is_decommissioned_vault.return_value = False
    config.is_decommissioning_vault.return_value = False
    config.whitelisted_assets = ["0xA"]
    config.hpke_public_key = b"\x01" * 32

    vault = MagicMock()
    vault.contract_address = "0xVault"
    vault.deposit_access_control = "0x0000000000000000000000000000000000000000"
    mock_resolve.return_value = vault

    MockLO.return_value.buffer_amount = 99
    MockLO.return_value.current_phase = 0

    snap = views.eligibility_snapshot()
    assert snap["is_system_idle"] is True
    assert snap["vault_type"] == "transparent"
    assert snap["lo_buffer_amount"] == 99


def test_decode_revert_system_not_idle():
    selector = function_signature_to_4byte_selector("SystemNotIdle()")
    assert decode_revert_data(selector) == "SystemNotIdle"
    assert "SystemNotIdle" in format_revert(selector)


def test_parse_lp_events_empty_receipt():
    w3 = MagicMock()
    receipt = {"logs": []}
    assert parse_lp_events_from_receipt(w3, receipt) == []


@patch("orion_finance_sdk_py.contracts.OrionVault._execute_vault_tx")
@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_vault_redeem_requires_decommissioned(MockConfig, mock_exec):
    MockConfig.return_value.is_orion_vault.return_value = True
    MockConfig.return_value.is_decommissioned_vault.return_value = False

    with patch.dict(
        os.environ,
        {
            "RPC_URL": "http://localhost:8545",
            "ORION_VAULT_ADDRESS": "0xVault",
            "LP_PRIVATE_KEY": "0xPrivate",
        },
    ):
        with patch("orion_finance_sdk_py.contracts.Web3") as MockWeb3:
            MockWeb3.HTTPProvider.return_value = MagicMock()
            w3 = MagicMock()
            w3.eth.chain_id = 11155111
            MockWeb3.return_value = w3
            MockWeb3.to_checksum_address.side_effect = lambda x: x
            with patch(
                "orion_finance_sdk_py.contracts.load_contract_abi",
                return_value=[],
            ):
                vault = OrionTransparentVault()
                with pytest.raises(ValueError, match="decommissioned"):
                    vault.redeem(1, "0xR", "0xO")
                mock_exec.assert_not_called()
