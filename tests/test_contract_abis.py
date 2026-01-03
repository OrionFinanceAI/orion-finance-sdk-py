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
        "OrionTransparentVault",
        "OrionEncryptedVault",
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


def test_invalid_abi_name():
    """Test that invalid ABI names raise appropriate exceptions."""
    with pytest.raises(Exception):
        load_contract_abi("NonExistentABI")
