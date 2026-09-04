"""Tests for vault_resolve helpers."""

import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.utils import checksum_address
from orion_finance_sdk_py.vault_resolve import resolve_vault

VAULT_LOWER = "0x6121eaa1d94a519653721904ceab48edd98f2c3a"
VAULT_CHECKSUM = checksum_address(VAULT_LOWER)
ENC_VAULT = "0x3333333333333333333333333333333333333333"
UNKNOWN_VAULT = "0x4444444444444444444444444444444444444444"


@patch("orion_finance_sdk_py.vault_resolve.OrionTransparentVault")
@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_from_env_transparent(MockConfig, MockTV):
    MockConfig.return_value.is_encrypted_vault.return_value = False
    MockConfig.return_value.is_orion_vault.return_value = True
    MockTV.return_value = MagicMock()

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": VAULT_CHECKSUM}):
        vault = resolve_vault()
    MockTV.assert_called_once_with(contract_address=VAULT_CHECKSUM)
    assert vault is MockTV.return_value


@patch("orion_finance_sdk_py.vault_resolve.OrionEncryptedVault")
@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_encrypted(MockConfig, MockEV):
    MockConfig.return_value.is_encrypted_vault.return_value = True
    MockEV.return_value = MagicMock()

    vault = resolve_vault(ENC_VAULT)
    MockEV.assert_called_once_with(contract_address=checksum_address(ENC_VAULT))
    assert vault is MockEV.return_value


@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_unknown_raises(MockConfig):
    MockConfig.return_value.is_encrypted_vault.return_value = False
    MockConfig.return_value.is_orion_vault.return_value = False
    with pytest.raises(ValueError, match="not in OrionConfig"):
        resolve_vault(UNKNOWN_VAULT)


def test_resolve_vault_missing_address_raises():
    with patch.dict(os.environ, {}, clear=True):
        # Ensure ORION_VAULT_ADDRESS unset
        os.environ.pop("ORION_VAULT_ADDRESS", None)
        with pytest.raises(ValueError, match="ORION_VAULT_ADDRESS"):
            resolve_vault()


@patch("orion_finance_sdk_py.vault_resolve.OrionTransparentVault")
@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_lowercase_env(MockConfig, MockTV):
    """Lowercase ORION_VAULT_ADDRESS is checksummed before registration checks."""
    MockConfig.return_value.is_encrypted_vault.return_value = False
    MockConfig.return_value.is_orion_vault.return_value = True
    MockTV.return_value = MagicMock()

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": VAULT_LOWER}):
        vault = resolve_vault()

    MockConfig.return_value.is_orion_vault.assert_called_with(VAULT_CHECKSUM)
    MockTV.assert_called_once_with(contract_address=VAULT_CHECKSUM)
    assert vault is MockTV.return_value
