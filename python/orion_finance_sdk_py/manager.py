"""Manager role helpers."""

from __future__ import annotations

from .contracts import (
    OrionConfig,
    TransactionResult,
    VaultFactory,
)
from .types import VaultType
from .vault_resolve import resolve_vault


def create_vault(
    *,
    vault_type: str = VaultType.TRANSPARENT.value,
    strategist_address: str,
    name: str,
    symbol: str,
    fee_type: int,
    performance_fee: int,
    management_fee: int,
    deposit_access_control: str,
) -> TransactionResult:
    """Create a transparent or encrypted vault via the matching factory."""
    factory = VaultFactory(vault_type=vault_type)
    return factory.create_orion_vault(
        strategist_address=strategist_address,
        name=name,
        symbol=symbol,
        fee_type=fee_type,
        performance_fee=performance_fee,
        management_fee=management_fee,
        deposit_access_control=deposit_access_control,
    )


def update_strategist(
    new_strategist_address: str,
    *,
    vault_address: str | None = None,
) -> TransactionResult:
    """Update the vault strategist."""
    vault = resolve_vault(vault_address)
    return vault.update_strategist(new_strategist_address)


def set_deposit_access_control(
    access_control_address: str,
    *,
    vault_address: str | None = None,
) -> TransactionResult:
    """Set vault deposit access control address (``address(0)`` = open)."""
    vault = resolve_vault(vault_address)
    return vault.set_deposit_access_control(access_control_address)


def update_fee_model(
    fee_type: int,
    performance_fee: int,
    management_fee: int,
    *,
    vault_address: str | None = None,
) -> TransactionResult:
    """Update the vault fee model."""
    vault = resolve_vault(vault_address)
    return vault.update_fee_model(fee_type, performance_fee, management_fee)


def claim_vault_fees(
    amount: int,
    *,
    vault_address: str | None = None,
) -> TransactionResult:
    """Claim pending vault manager fees."""
    vault = resolve_vault(vault_address)
    return vault.transfer_manager_fees(amount)


def remove_orion_vault(vault_address: str | None = None) -> TransactionResult:
    """Initiate vault decommissioning via ``OrionConfig.removeOrionVault``."""
    vault = resolve_vault(vault_address)
    config = OrionConfig()
    return config.remove_orion_vault(vault.contract_address)
