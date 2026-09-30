"""Execution cost types (adapter vs oracle)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCost:
    """Estimated buy-side execution cost of an asset trade.

    ``cost_pct`` is the ``previewBuy`` quote versus price-adapter fair value
    (positive means worse than oracle). That gap embeds LP fees, slippage,
    and other venue effects on the Orion execution path.
    """

    symbol: str
    asset: str
    size: float
    netting_eta: float
    swap_size: float
    shares: int
    cost_pct: float
    execution_underlying: int
    fair_underlying: int
    price: int
    execution_adapter: str
    block: int | None
