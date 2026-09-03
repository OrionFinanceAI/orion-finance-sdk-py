"""LP (liquidity provider) role helpers."""

from __future__ import annotations

from .console_ui import progress_step
from .contracts import OrionConfig, SystemNotIdleError, TransactionResult
from .erc20 import approve
from .vault_resolve import resolve_vault


def request_deposit(
    assets: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Approve underlying to the vault, then ``requestDeposit``."""
    config = OrionConfig()
    progress_step("Verifying protocol is idle")
    if not config.is_system_idle():
        raise SystemNotIdleError(
            "System is not idle. Cannot request deposit at this time."
        )
    if assets < config.min_deposit_amount:
        raise ValueError(
            f"assets {assets} below minDepositAmount {config.min_deposit_amount}"
        )

    vault = resolve_vault(vault_address)
    progress_step("Checking vault decommission status")
    if config.is_decommissioning_vault(vault.contract_address) or (
        config.is_decommissioned_vault(vault.contract_address)
    ):
        raise ValueError(
            "Cannot request deposit while vault is decommissioning/decommissioned."
        )

    progress_step("Approving underlying token allowance")
    approve(
        vault.w3,
        config.underlying_asset,
        vault.contract_address,
        assets,
        key_env=key_env,
    )
    return vault.request_deposit(assets, key_env=key_env)


def cancel_deposit_request(
    amount: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Cancel a pending deposit request."""
    config = OrionConfig()
    if not config.is_system_idle():
        raise SystemNotIdleError(
            "System is not idle. Cannot cancel deposit request at this time."
        )
    vault = resolve_vault(vault_address)
    return vault.cancel_deposit_request(amount, key_env=key_env)


def request_redeem(
    shares: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Approve vault shares to the vault, then ``requestRedeem``."""
    config = OrionConfig()
    progress_step("Verifying protocol is idle")
    if not config.is_system_idle():
        raise SystemNotIdleError(
            "System is not idle. Cannot request redeem at this time."
        )
    if shares < config.min_redeem_amount:
        raise ValueError(
            f"shares {shares} below minRedeemAmount {config.min_redeem_amount}"
        )

    vault = resolve_vault(vault_address)
    progress_step("Checking vault decommission status")
    if config.is_decommissioned_vault(vault.contract_address):
        raise ValueError(
            "Vault is decommissioned. Use redeem() for sync exit instead of request_redeem."
        )

    progress_step("Approving vault share allowance")
    approve(
        vault.w3,
        vault.contract_address,
        vault.contract_address,
        shares,
        key_env=key_env,
    )
    return vault.request_redeem(shares, key_env=key_env)


def cancel_redeem_request(
    shares: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Cancel a pending redeem request."""
    config = OrionConfig()
    if not config.is_system_idle():
        raise SystemNotIdleError(
            "System is not idle. Cannot cancel redeem request at this time."
        )
    vault = resolve_vault(vault_address)
    return vault.cancel_redeem_request(shares, key_env=key_env)


def redeem(
    shares: int,
    receiver: str,
    owner: str,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Sync redeem after vault decommissioning."""
    vault = resolve_vault(vault_address)
    return vault.redeem(shares, receiver, owner, key_env=key_env)


def approve_shares(
    spender: str,
    amount: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Approve spender for vault shares."""
    vault = resolve_vault(vault_address)
    return vault.approve_shares(spender, amount, key_env=key_env)


def transfer_shares(
    to: str,
    amount: int,
    *,
    vault_address: str | None = None,
    key_env: str = "LP_PRIVATE_KEY",
) -> TransactionResult:
    """Transfer vault shares."""
    vault = resolve_vault(vault_address)
    return vault.transfer_shares(to, amount, key_env=key_env)
