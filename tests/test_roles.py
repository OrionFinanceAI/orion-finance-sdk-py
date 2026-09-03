"""Tests for role-scoped LP / manager / strategist APIs."""

import os
from unittest.mock import MagicMock, PropertyMock, patch

import orion_finance_sdk_py.errors as errors_mod
import pytest
from eth_utils import function_signature_to_4byte_selector
from orion_finance_sdk_py import lp, manager, strategist, views
from orion_finance_sdk_py.contracts import (
    OrionTransparentVault,
    SystemNotIdleError,
    TransactionResult,
)
from orion_finance_sdk_py.errors import (
    ContractError,
    _error_selector_map,
    decode_revert_data,
    format_revert,
)
from orion_finance_sdk_py.events import parse_lp_events_from_receipt
from orion_finance_sdk_py.types import ZERO_ADDRESS


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
    factory.create_orion_vault.assert_called_once_with(
        strategist_address="0xS",
        name="Priv",
        symbol="P",
        fee_type=0,
        performance_fee=100,
        management_fee=10,
        deposit_access_control="0x0",
        holder_access_control=ZERO_ADDRESS,
        transfer_access_control=ZERO_ADDRESS,
    )


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


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_deposit_below_min(MockConfig, mock_resolve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 100
    with pytest.raises(ValueError, match="below minDepositAmount"):
        lp.request_deposit(10)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_deposit_rejects_decommissioning(MockConfig, mock_resolve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 1
    config.is_decommissioning_vault.return_value = True
    config.is_decommissioned_vault.return_value = False
    vault = MagicMock()
    vault.contract_address = "0xVault"
    mock_resolve.return_value = vault
    with pytest.raises(ValueError, match="decommissioning"):
        lp.request_deposit(10)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_redeem_below_min(MockConfig, mock_resolve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_redeem_amount = 50
    with pytest.raises(ValueError, match="below minRedeemAmount"):
        lp.request_redeem(1)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_redeem_rejects_decommissioned(MockConfig, mock_resolve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_redeem_amount = 1
    config.is_decommissioned_vault.return_value = True
    vault = MagicMock()
    vault.contract_address = "0xVault"
    mock_resolve.return_value = vault
    with pytest.raises(ValueError, match="decommissioned"):
        lp.request_redeem(10)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_cancel_deposit_and_redeem(MockConfig, mock_resolve):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    vault = MagicMock()
    vault.cancel_deposit_request.return_value = TransactionResult(
        tx_hash="0xcd", receipt={"status": 1}, decoded_logs=[]
    )
    vault.cancel_redeem_request.return_value = TransactionResult(
        tx_hash="0xcr", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    lp.cancel_deposit_request(5)
    vault.cancel_deposit_request.assert_called_once_with(5, key_env="LP_PRIVATE_KEY")
    lp.cancel_redeem_request(7)
    vault.cancel_redeem_request.assert_called_once_with(7, key_env="LP_PRIVATE_KEY")


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_cancel_deposit_not_idle(MockConfig, mock_resolve):
    MockConfig.return_value.is_system_idle.return_value = False
    with pytest.raises(SystemNotIdleError):
        lp.cancel_deposit_request(1)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_cancel_redeem_not_idle(MockConfig, mock_resolve):
    MockConfig.return_value.is_system_idle.return_value = False
    with pytest.raises(SystemNotIdleError):
        lp.cancel_redeem_request(1)


@patch("orion_finance_sdk_py.lp.resolve_vault")
@patch("orion_finance_sdk_py.lp.OrionConfig")
def test_lp_request_redeem_not_idle(MockConfig, mock_resolve):
    MockConfig.return_value.is_system_idle.return_value = False
    with pytest.raises(SystemNotIdleError):
        lp.request_redeem(1)


@patch("orion_finance_sdk_py.lp.resolve_vault")
def test_lp_approve_and_transfer_shares(mock_resolve):
    vault = MagicMock()
    vault.approve_shares.return_value = TransactionResult(
        tx_hash="0xa", receipt={"status": 1}, decoded_logs=[]
    )
    vault.transfer_shares.return_value = TransactionResult(
        tx_hash="0xt", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    lp.approve_shares("0xSpender", 10)
    vault.approve_shares.assert_called_once_with(
        "0xSpender", 10, key_env="LP_PRIVATE_KEY"
    )
    lp.transfer_shares("0xTo", 3)
    vault.transfer_shares.assert_called_once_with("0xTo", 3, key_env="LP_PRIVATE_KEY")


@patch("orion_finance_sdk_py.manager.resolve_vault")
def test_manager_update_strategist_and_fee_and_dac(mock_resolve):
    vault = MagicMock()
    vault.update_strategist.return_value = TransactionResult(
        tx_hash="0xs", receipt={"status": 1}, decoded_logs=[]
    )
    vault.set_deposit_access_control.return_value = TransactionResult(
        tx_hash="0xd", receipt={"status": 1}, decoded_logs=[]
    )
    vault.update_fee_model.return_value = TransactionResult(
        tx_hash="0xf", receipt={"status": 1}, decoded_logs=[]
    )
    vault.transfer_manager_fees.return_value = TransactionResult(
        tx_hash="0xc", receipt={"status": 1}, decoded_logs=[]
    )
    mock_resolve.return_value = vault

    manager.update_strategist("0xNew")
    vault.update_strategist.assert_called_once_with("0xNew")
    manager.set_deposit_access_control("0xAcl")
    vault.set_deposit_access_control.assert_called_once_with("0xAcl")
    manager.set_holder_access_control("0xHolder")
    vault.set_holder_access_control.assert_called_once_with("0xHolder")
    manager.set_transfer_access_control("0xTransfer")
    vault.set_transfer_access_control.assert_called_once_with("0xTransfer")
    manager.update_fee_model(0, 100, 10)
    vault.update_fee_model.assert_called_once_with(0, 100, 10)
    manager.claim_vault_fees(42)
    vault.transfer_manager_fees.assert_called_once_with(42)


@patch("orion_finance_sdk_py.views.OrionConfig")
def test_views_thin_helpers(MockConfig):
    config = MockConfig.return_value
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 11
    config.min_redeem_amount = 22
    config.hpke_public_key = b"\x02" * 32
    config.whitelisted_assets = ["0xA", "0xB"]

    assert views.is_system_idle() is True
    assert views.min_deposit_amount() == 11
    assert views.min_redeem_amount() == 22
    assert views.hpke_public_key() == b"\x02" * 32
    assert views.whitelisted_assets() == ["0xA", "0xB"]


@patch("orion_finance_sdk_py.views.resolve_vault")
@patch("orion_finance_sdk_py.views.OrionConfig")
def test_views_vault_type_and_decommission_flags(MockConfig, mock_resolve):
    vault = MagicMock()
    vault.contract_address = "0xVault"
    vault.deposit_access_control = "0xAcl"
    mock_resolve.return_value = vault

    config = MockConfig.return_value
    config.is_encrypted_vault.return_value = True
    config.is_decommissioned_vault.return_value = True
    config.is_decommissioning_vault.return_value = False

    assert views.vault_type() == "encrypted"
    assert views.is_decommissioned() is True
    assert views.is_decommissioning() is False
    assert views.deposit_access_control() == "0xAcl"

    config.is_encrypted_vault.return_value = False
    assert views.vault_type() == "transparent"


@patch("orion_finance_sdk_py.views.LiquidityOrchestrator")
def test_views_lo_helpers(MockLO):
    MockLO.return_value.buffer_amount = 5
    MockLO.return_value.get_epoch_state.return_value = {"phase": 1}
    assert views.lo_buffer_amount() == 5
    assert views.lo_epoch_state() == {"phase": 1}


@patch("orion_finance_sdk_py.views.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.views.resolve_vault")
@patch("orion_finance_sdk_py.views.OrionConfig")
def test_views_eligibility_snapshot_hpke_error(MockConfig, mock_resolve, MockLO):
    config = MockConfig.return_value
    type(config).hpke_public_key = PropertyMock(side_effect=ValueError("bad key"))
    config.is_system_idle.return_value = True
    config.min_deposit_amount = 1
    config.min_redeem_amount = 1
    config.is_encrypted_vault.return_value = True
    config.is_decommissioned_vault.return_value = False
    config.is_decommissioning_vault.return_value = False
    config.whitelisted_assets = []

    vault = MagicMock()
    vault.contract_address = "0xEnc"
    vault.deposit_access_control = "0x0"
    mock_resolve.return_value = vault
    MockLO.return_value.buffer_amount = 0
    MockLO.return_value.current_phase = 2

    snap = views.eligibility_snapshot()
    assert snap["hpke_public_key"] is None
    assert snap["vault_type"] == "encrypted"
    assert snap["lo_current_phase"] == 2


def test_decode_revert_edge_cases():
    assert decode_revert_data(None) is None
    assert decode_revert_data("not-hex") is None
    assert decode_revert_data(b"\x01\x02") is None
    assert decode_revert_data("0xdeadbeef") is None
    assert format_revert(None) == "Transaction reverted"
    assert format_revert(b"\x01\x02", fallback="oops") == "oops"


def test_contract_error_message():
    err = ContractError("SystemNotIdle")
    assert err.error_name == "SystemNotIdle"
    assert str(err) == "SystemNotIdle"
    err2 = ContractError("X", message="custom")
    assert str(err2) == "custom"


def test_error_selector_map_abi_load_failure(monkeypatch):
    errors_mod._SELECTOR_TO_NAME = None

    def boom(_name):
        raise RuntimeError("missing abi")

    monkeypatch.setattr(errors_mod, "load_contract_abi", boom)
    assert _error_selector_map() == {}
    # cached empty
    assert _error_selector_map() == {}
    errors_mod._SELECTOR_TO_NAME = None
