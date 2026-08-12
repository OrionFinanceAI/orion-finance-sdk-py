"""Shared vault address resolution helpers."""

from __future__ import annotations

import os

from .contracts import (
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
)
from .utils import validate_var


def resolve_vault(
    vault_address: str | None = None,
) -> OrionTransparentVault | OrionEncryptedVault:
    """Return the typed vault wrapper for a registered Orion vault."""
    address = validate_var(
        vault_address or os.getenv("ORION_VAULT_ADDRESS"),
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Pass vault_address=... or set ORION_VAULT_ADDRESS."
        ),
    )
    config = OrionConfig()
    if config.is_encrypted_vault(address):
        return OrionEncryptedVault(contract_address=address)
    if config.is_orion_vault(address):
        return OrionTransparentVault(contract_address=address)
    raise ValueError(f"Vault address {address} not in OrionConfig contract.")
