"""Strategist role helpers."""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import TransactionResult
from .vault_resolve import resolve_vault


def submit_intent(
    order_intent: Mapping[str, int],
    *,
    vault_address: str | None = None,
) -> TransactionResult | None:
    """Submit a scaled plaintext intent; encrypts automatically for encrypted vaults.

    Returns ``None`` when a transparent vault already holds the same intent.
    """
    vault = resolve_vault(vault_address)
    return vault.submit_order_intent(dict(order_intent))
