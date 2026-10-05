"""Execution cost types (adapter vs oracle)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCost:
    """Estimated execution cost of an asset trade (buy or sell).

    ``cost_pct`` compares the adapter quote to price-adapter fair value
    (positive means worse than oracle):

    * **buy:** ``(execution - fair) / fair`` — pays more underlying than mark
    * **sell:** ``(fair - execution) / fair`` — receives less underlying than mark

    That gap embeds LP fees, slippage, and other venue effects on the Orion
    execution path. Buys use ``previewBuy``; sells simulate ``sell`` via
    ``eth_call`` with ERC-20 state overrides (no onchain ``previewSell``).
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
    side: str = "buy"
