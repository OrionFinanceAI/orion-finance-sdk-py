"""Read helpers for LP / manager / strategist eligibility and discovery."""

from __future__ import annotations

from .contracts import LiquidityOrchestrator, OrionConfig
from .vault_resolve import resolve_vault


def is_system_idle() -> bool:
    """Whether the protocol is Idle (required for most writes)."""
    return OrionConfig().is_system_idle()


def min_deposit_amount() -> int:
    """Protocol minimum deposit (underlying units)."""
    return OrionConfig().min_deposit_amount


def min_redeem_amount() -> int:
    """Protocol minimum redeem (share units)."""
    return OrionConfig().min_redeem_amount


def hpke_public_key() -> bytes:
    """Orion HPKE recipient public key (32 bytes)."""
    return OrionConfig().hpke_public_key


def whitelisted_assets() -> list[str]:
    """Investment universe token addresses."""
    return OrionConfig().whitelisted_assets


def vault_type(vault_address: str | None = None) -> str:
    """Return ``"encrypted"`` or ``"transparent"`` for a registered vault."""
    vault = resolve_vault(vault_address)
    config = OrionConfig()
    if config.is_encrypted_vault(vault.contract_address):
        return "encrypted"
    return "transparent"


def is_decommissioned(vault_address: str | None = None) -> bool:
    """Whether the vault is fully decommissioned."""
    vault = resolve_vault(vault_address)
    return OrionConfig().is_decommissioned_vault(vault.contract_address)


def is_decommissioning(vault_address: str | None = None) -> bool:
    """Whether the vault is decommissioning."""
    vault = resolve_vault(vault_address)
    return OrionConfig().is_decommissioning_vault(vault.contract_address)


def deposit_access_control(vault_address: str | None = None) -> str:
    """Vault deposit ACL address (``address(0)`` if permissionless deposits)."""
    return resolve_vault(vault_address).deposit_access_control


def lo_buffer_amount() -> int:
    """Return the LiquidityOrchestrator underlying buffer amount."""
    return LiquidityOrchestrator().buffer_amount


def lo_epoch_state() -> dict:
    """Return the LiquidityOrchestrator epoch state dict."""
    return LiquidityOrchestrator().get_epoch_state()


def eligibility_snapshot(vault_address: str | None = None) -> dict:
    """Bundle common eligibility reads for UX."""
    config = OrionConfig()
    vault = resolve_vault(vault_address)
    try:
        hpke_key: bytes | None = config.hpke_public_key
    except ValueError:
        hpke_key = None
    return {
        "is_system_idle": config.is_system_idle(),
        "min_deposit_amount": config.min_deposit_amount,
        "min_redeem_amount": config.min_redeem_amount,
        "vault_type": (
            "encrypted"
            if config.is_encrypted_vault(vault.contract_address)
            else "transparent"
        ),
        "is_decommissioned": config.is_decommissioned_vault(vault.contract_address),
        "is_decommissioning": config.is_decommissioning_vault(vault.contract_address),
        "deposit_access_control": vault.deposit_access_control,
        "hpke_public_key": hpke_key,
        "whitelisted_assets": config.whitelisted_assets,
        "lo_buffer_amount": LiquidityOrchestrator().buffer_amount,
        "lo_current_phase": LiquidityOrchestrator().current_phase,
    }
