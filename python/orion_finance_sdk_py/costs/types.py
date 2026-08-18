"""Venue-agnostic execution cost types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCost:
    """Estimated execution cost of a signed asset trade.

    Fields apply to any venue and any vault.
    """

    symbol: str
    timestamp: str
    signed_size: float
    netting_eta: float
    swap_size: float
    fee_pct: float
    slippage_pct: float
    cost_pct: float
    amount_in: float
    amount_out: float
