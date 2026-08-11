"""Tests for vault_resolve helpers."""

import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.vault_resolve import resolve_vault


@patch("orion_finance_sdk_py.vault_resolve.OrionTransparentVault")
@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_from_env_transparent(MockConfig, MockTV):
    MockConfig.return_value.is_encrypted_vault.return_value = False
    MockConfig.return_value.is_orion_vault.return_value = True
    MockTV.return_value = MagicMock()

    with patch.dict(os.environ, {"ORION_VAULT_ADDRESS": "0xVault"}):
        vault = resolve_vault()
    MockTV.assert_called_once_with(contract_address="0xVault")
    assert vault is MockTV.return_value


@patch("orion_finance_sdk_py.vault_resolve.OrionEncryptedVault")
@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_encrypted(MockConfig, MockEV):
    MockConfig.return_value.is_encrypted_vault.return_value = True
    MockEV.return_value = MagicMock()

    vault = resolve_vault("0xEnc")
    MockEV.assert_called_once_with(contract_address="0xEnc")
    assert vault is MockEV.return_value


@patch("orion_finance_sdk_py.vault_resolve.OrionConfig")
def test_resolve_vault_unknown_raises(MockConfig):
    MockConfig.return_value.is_encrypted_vault.return_value = False
    MockConfig.return_value.is_orion_vault.return_value = False
    with pytest.raises(ValueError, match="not in OrionConfig"):
        resolve_vault("0xUnknown")


def test_resolve_vault_missing_address_raises():
    with patch.dict(os.environ, {}, clear=True):
        # Ensure ORION_VAULT_ADDRESS unset
        os.environ.pop("ORION_VAULT_ADDRESS", None)
        with pytest.raises(ValueError, match="ORION_VAULT_ADDRESS"):
            resolve_vault()
