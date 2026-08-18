"""Estimate execution cost of a signed asset trade."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from web3 import Web3

from orion_finance_sdk_py.costs.dates import parse_cost_timestamp
from orion_finance_sdk_py.costs.registry import (
    VenueAsset,
    looks_like_address,
    resolve_symbol,
    resolve_symbol_onchain,
)
from orion_finance_sdk_py.costs.types import ExecutionCost
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import USDC_ADDRESS
from orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state import (
    PoolMeta,
    PoolState,
    enrich_pool_meta,
    fetch_pool_state,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.rpc import connect_mainnet
from orion_finance_sdk_py.costs.venues.uniswap_v3.simulator import simulate_asset_swap
from orion_finance_sdk_py.rpc import block_at_timestamp

load_dotenv()

_SUPPORTED_VENUES = frozenset({"uniswap_v3"})


class ExecutionCostEstimator:
    """Manager-facing execution cost estimator.

    v1 wraps Uniswap v3 on Ethereum mainnet (the venue Orion will use). Set
    ``MAINNET_RPC_URL`` to an archival endpoint. Optional ``block_number`` pins
    snapshots for research reproducibility and is not part of ``get_cost``.
    """

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        block_number: int | None = None,
    ) -> None:
        """Initialize with an optional RPC URL and pinned block."""
        self._rpc_url = (rpc_url or os.environ.get("MAINNET_RPC_URL") or "").strip()
        self._block_override = block_number
        self._w3: Web3 | None = None
        self._snapshots: dict[tuple[str, int], PoolState] = {}
        self._extra_assets: dict[str, VenueAsset] = {}

    def _web3(self) -> Web3:
        if self._w3 is None:
            if not self._rpc_url:
                raise RuntimeError(
                    "MAINNET_RPC_URL is required for execution cost estimates. "
                    "Set it to an archival Ethereum mainnet RPC."
                )
            self._w3 = connect_mainnet(self._rpc_url)
        return self._w3

    def preload_uniswap_state(self, symbol: str, state: PoolState) -> None:
        """Inject a pool snapshot (tests and research pipelines)."""
        spec = self._spec_from_preloaded_state(symbol, state)
        pool_mismatch = spec.pool.lower() != str(state.meta.address).lower()
        fee_mismatch = int(spec.fee) != int(state.meta.fee)
        if pool_mismatch or fee_mismatch:
            raise ValueError(
                f"Preloaded pool {state.meta.address} fee={state.meta.fee} "
                f"does not match {symbol} pool {spec.pool} fee={spec.fee}"
            )
        self._extra_assets[spec.symbol.upper()] = spec
        self._extra_assets[spec.address.lower()] = spec
        self._snapshots[(spec.pool.lower(), state.block_number)] = state

    def _spec_from_preloaded_state(self, symbol: str, state: PoolState) -> VenueAsset:
        try:
            return resolve_symbol(symbol)
        except KeyError:
            pass
        usdc = USDC_ADDRESS.lower()
        t0, t1 = state.meta.token0.lower(), state.meta.token1.lower()
        if t0 == usdc:
            address, ticker = state.meta.token1, state.meta.symbol1 or symbol
        elif t1 == usdc:
            address, ticker = state.meta.token0, state.meta.symbol0 or symbol
        else:
            raise ValueError(f"Preloaded pool {state.meta.address} is not an USDC pair")
        if looks_like_address(str(symbol).strip()):
            address = Web3.to_checksum_address(symbol)
        return VenueAsset(
            symbol=str(ticker),
            address=Web3.to_checksum_address(address),
            pool=Web3.to_checksum_address(state.meta.address),
            fee=int(state.meta.fee),
        )

    def get_cost(
        self,
        symbol: str,
        signed_size: float,
        timestamp: str | None = None,
        *,
        netting_eta: float = 0.0,
        venue: str = "uniswap_v3",
    ) -> ExecutionCost:
        """Estimate execution cost of a signed trade in human asset units.

        Args:
            symbol: Ticker (e.g. ``WETH``, ``WBTC``) or mainnet token address.
            signed_size: Human units of the risk asset. Positive buys (exact
                output), negative sells (exact input).
            timestamp: UTC calendar date ``YYYY-MM-DD``. ``None`` means now.
            netting_eta: Fraction of the nominal size that is internally
                netted. The venue swap is ``(1 - eta) * signed_size``; cost
                percentages are those of that swap, not scaled by ``(1-eta)``.
            venue: Backend selector. Only ``uniswap_v3`` is implemented.
        """
        if venue not in _SUPPORTED_VENUES:
            raise ValueError(
                f"Unsupported venue {venue!r}. v1 supports uniswap_v3 only."
            )
        size = float(signed_size)
        if not math.isfinite(size) or size == 0:
            raise ValueError("signed_size must be non-zero")
        if not 0.0 <= float(netting_eta) <= 1.0:
            raise ValueError("netting_eta must be in [0, 1]")

        as_of, unix = parse_cost_timestamp(timestamp)
        swap_size = (1.0 - float(netting_eta)) * size
        block = self._block_override
        if block is not None:
            as_of = self._date_at_block(block)
        if swap_size == 0:
            return ExecutionCost(
                symbol=str(symbol).strip(),
                timestamp=as_of,
                signed_size=size,
                netting_eta=float(netting_eta),
                swap_size=0.0,
                fee_pct=0.0,
                slippage_pct=0.0,
                cost_pct=0.0,
                amount_in=0.0,
                amount_out=0.0,
            )

        if block is None:
            block = self._resolve_block(unix)
        spec = self._resolve_asset(symbol, block)
        state = self._snapshot(spec, block)
        result = simulate_asset_swap(state, spec.address, swap_size)
        return ExecutionCost(
            symbol=spec.symbol,
            timestamp=as_of,
            signed_size=size,
            netting_eta=float(netting_eta),
            swap_size=swap_size,
            fee_pct=result.fee_pct,
            slippage_pct=result.slippage_pct,
            cost_pct=result.cost_pct,
            amount_in=result.amount_in,
            amount_out=result.amount_out,
        )

    def _resolve_asset(self, symbol: str, block: int) -> VenueAsset:
        raw = str(symbol).strip()
        extra = self._extra_assets.get(raw.upper()) or self._extra_assets.get(
            raw.lower()
        )
        if extra is not None:
            return extra
        try:
            return resolve_symbol(symbol)
        except KeyError:
            if not looks_like_address(raw):
                raise
            return resolve_symbol_onchain(symbol, self._web3(), block)

    def _resolve_block(self, unix: int) -> int:
        if self._block_override is not None:
            return self._block_override
        return block_at_timestamp(self._web3(), unix)

    def _date_at_block(self, block: int) -> str:
        header = self._web3().eth.get_block(block)
        return datetime.fromtimestamp(
            int(header["timestamp"]), tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def _snapshot(self, spec: VenueAsset, block: int) -> PoolState:
        key = (spec.pool.lower(), block)
        cached = self._snapshots.get(key)
        if cached is not None:
            return cached

        w3 = self._web3()
        meta = PoolMeta(address=Web3.to_checksum_address(spec.pool), fee=spec.fee)
        enrich_pool_meta(w3, meta, block)
        state = fetch_pool_state(w3, meta, block)
        if state.liquidity == 0:
            raise RuntimeError(
                f"Uniswap v3 pool {spec.pool} has zero liquidity at block {block}"
            )
        self._snapshots[key] = state
        return state


_DEFAULT_ESTIMATOR: ExecutionCostEstimator | None = None


def get_cost(
    symbol: str,
    signed_size: float,
    timestamp: str | None = None,
    *,
    netting_eta: float = 0.0,
    venue: str = "uniswap_v3",
) -> ExecutionCost:
    """Module-level wrapper around a process-default :class:`ExecutionCostEstimator`."""
    global _DEFAULT_ESTIMATOR
    if _DEFAULT_ESTIMATOR is None:
        _DEFAULT_ESTIMATOR = ExecutionCostEstimator()
    return _DEFAULT_ESTIMATOR.get_cost(
        symbol,
        signed_size,
        timestamp,
        netting_eta=netting_eta,
        venue=venue,
    )
