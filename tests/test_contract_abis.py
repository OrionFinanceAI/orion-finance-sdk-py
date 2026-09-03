"""Test module to verify ABI loading works in installed package."""

import pytest
from orion_finance_sdk_py.contracts import load_contract_abi


def test_abi_import():
    """Test that the ABI loading function can be imported."""
    from orion_finance_sdk_py.contracts import load_contract_abi

    assert callable(load_contract_abi)


def test_abi_loading():
    """Test loading each ABI file."""
    abis = [
        "OrionConfig",
        "TransparentVaultFactory",
        "EncryptedVaultFactory",
        "OrionVault",
        "OrionTransparentVault",
        "OrionEncryptedVault",
        "LiquidityOrchestrator",
        "PriceAdapterRegistry",
        "ErrorsLib",
        "IOrionDepositAccessControl",
        "IOrionHolderAccessControl",
        "IOrionTransferAccessControl",
    ]

    for abi_name in abis:
        abi = load_contract_abi(abi_name)
        assert isinstance(abi, list), f"{abi_name} ABI should be a list"
        assert len(abi) > 0, f"{abi_name} ABI should not be empty"


def test_abi_structure():
    """Test that loaded ABIs have the expected structure."""
    abi = load_contract_abi("OrionConfig")

    # Check that ABI contains expected fields for contract functions
    assert isinstance(abi, list), "ABI should be a list"

    # Check that at least some items have the expected structure
    function_items = [
        item
        for item in abi
        if isinstance(item, dict) and item.get("type") == "function"
    ]
    assert len(function_items) > 0, "ABI should contain function definitions"


def _create_vault_inputs(factory_name: str) -> list[str]:
    abi = load_contract_abi(factory_name)
    create = next(
        item
        for item in abi
        if item.get("type") == "function" and item.get("name") == "createVault"
    )
    return [inp["name"] for inp in create["inputs"]]


def test_factory_create_vault_has_nine_inputs():
    expected = [
        "strategist",
        "name",
        "symbol",
        "feeType",
        "performanceFee",
        "managementFee",
        "depositAccessControl",
        "holderAccessControl",
        "transferAccessControl",
    ]
    assert _create_vault_inputs("TransparentVaultFactory") == expected
    assert _create_vault_inputs("EncryptedVaultFactory") == expected


def test_vault_abi_includes_272_methods():
    abi = load_contract_abi("OrionVault")
    names = {
        item["name"]
        for item in abi
        if isinstance(item, dict) and item.get("type") == "function"
    }
    for name in (
        "requestDepositFor",
        "pendingUnderlyingClaim",
        "setHolderAccessControl",
        "setTransferAccessControl",
        "holderAccessControl",
        "transferAccessControl",
        "claimUnderlying",
    ):
        assert name in names, f"OrionVault ABI missing {name}"


def test_access_control_interface_abis():
    """Interface ABIs from abis-v2.7.2 include the ACL view methods."""
    deposit = {
        item["name"]
        for item in load_contract_abi("IOrionDepositAccessControl")
        if item.get("type") == "function"
    }
    holder = {
        item["name"]
        for item in load_contract_abi("IOrionHolderAccessControl")
        if item.get("type") == "function"
    }
    transfer = {
        item["name"]
        for item in load_contract_abi("IOrionTransferAccessControl")
        if item.get("type") == "function"
    }
    assert "canRequestDeposit" in deposit
    assert "canHoldShares" in holder
    assert "canTransferShares" in transfer


def test_invalid_abi_name():
    """Test that invalid ABI names raise appropriate exceptions."""
    with pytest.raises(Exception):
        load_contract_abi("NonExistentABI")
