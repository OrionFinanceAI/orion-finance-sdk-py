"""Uniswap v3 swap simulation matching Orion's execution adapter.

Buy (positive size) is exact-output of the risk asset. Sell (negative size)
is exact-input of the risk asset. Quote asset is the pool's USDC side.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
    Q96,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state import PoolState
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.swap_math import (
    compute_swap_step,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.tick_math import (
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
)


@dataclass(frozen=True)
class SwapResult:
    """Amounts and cost breakdown for a simulated Uniswap v3 swap."""

    amount_in: float
    amount_out: float
    amount_in_raw: int
    amount_out_raw: int
    fee_raw: int
    fee_pct: float
    slippage_pct: float
    cost_pct: float


def sqrt_price_to_price_ratio(state: PoolState) -> float:
    """Human token1 per token0."""
    meta = state.meta
    ratio = (state.sqrt_price_x96 / Q96) ** 2
    return ratio * (10 ** (meta.decimals0 - meta.decimals1))


def token_usd_prices(state: PoolState) -> tuple[float, float]:
    """USD prices of (token0, token1). USDC is $1; the other side is AMM mid."""
    ratio = sqrt_price_to_price_ratio(state)
    anchor = (state.meta.stable_token or "").lower()
    t0 = state.meta.token0.lower()
    t1 = state.meta.token1.lower()
    if anchor == t0:
        return 1.0, (1.0 / ratio if ratio else 0.0)
    if anchor == t1:
        return (ratio if ratio else 0.0), 1.0
    raise ValueError(f"Pool {state.meta.address} is not a USDC pair")


def _next_initialized_tick(
    initialized_ticks: list[int], tick: int, zero_for_one: bool
) -> int:
    if zero_for_one:
        below = [t for t in initialized_ticks if t < tick]
        return max(below) if below else MIN_TICK
    above = [t for t in initialized_ticks if t > tick]
    return min(above) if above else MAX_TICK


def _add_liquidity_delta(liquidity: int, delta: int) -> int:
    result = liquidity + delta
    if result < 0:
        raise ValueError("liquidity underflow")
    return result


def _walk_swap(
    state: PoolState,
    amount_remaining: int,
    zero_for_one: bool,
    sqrt_price_limit_x96: int | None = None,
) -> tuple[int, int, int, int]:
    """Walk ticks. Returns (amount_in_incl_fee, amount_out, fee_total, sqrt)."""
    exact_in = amount_remaining >= 0
    if amount_remaining == 0:
        return 0, 0, 0, state.sqrt_price_x96

    if sqrt_price_limit_x96 is None:
        sqrt_price_limit_x96 = (
            MIN_SQRT_RATIO + 1 if zero_for_one else MAX_SQRT_RATIO - 1
        )

    if zero_for_one:
        sqrt_price_limit_x96 = max(sqrt_price_limit_x96, MIN_SQRT_RATIO + 1)
    else:
        sqrt_price_limit_x96 = min(sqrt_price_limit_x96, MAX_SQRT_RATIO - 1)

    sqrt_price_x96 = state.sqrt_price_x96
    tick = state.tick
    liquidity = state.liquidity
    remaining = amount_remaining
    amount_in_total = 0
    amount_out_total = 0
    fee_total = 0
    fee_pips = state.meta.fee
    ticks = state.initialized_ticks
    tick_net = state.tick_liquidity_net

    while remaining != 0 and sqrt_price_x96 != sqrt_price_limit_x96:
        if exact_in and remaining <= 0:
            break
        if not exact_in and remaining >= 0:
            break

        tick_next = _next_initialized_tick(ticks, tick, zero_for_one)
        sqrt_price_next = get_sqrt_ratio_at_tick(tick_next)
        sqrt_price_target = (
            max(sqrt_price_next, sqrt_price_limit_x96)
            if zero_for_one
            else min(sqrt_price_next, sqrt_price_limit_x96)
        )

        sqrt_price_x96, step_in, step_out, fee_amount = compute_swap_step(
            sqrt_price_x96,
            sqrt_price_target,
            liquidity,
            remaining,
            fee_pips,
        )
        if exact_in:
            remaining -= step_in + fee_amount
        else:
            remaining += step_out
        amount_in_total += step_in + fee_amount
        amount_out_total += step_out
        fee_total += fee_amount

        if sqrt_price_x96 == sqrt_price_next:
            if tick_next in tick_net:
                net = tick_net[tick_next]
                if zero_for_one:
                    net = -net
                liquidity = _add_liquidity_delta(liquidity, net)
            tick = tick_next - 1 if zero_for_one else tick_next
        else:
            tick = get_tick_at_sqrt_ratio(sqrt_price_x96)

    return amount_in_total, amount_out_total, fee_total, sqrt_price_x96


def _asset_side(state: PoolState, asset: str) -> tuple[bool, int]:
    """Return (asset_is_token0, asset_decimals)."""
    asset_l = asset.lower()
    t0 = state.meta.token0.lower()
    t1 = state.meta.token1.lower()
    if asset_l == t0:
        return True, state.meta.decimals0
    if asset_l == t1:
        return False, state.meta.decimals1
    raise ValueError(
        f"Asset {asset} is not in pool {state.meta.address} "
        f"({state.meta.token0}/{state.meta.token1})"
    )


def _cost_breakdown(
    usd_in: float, usd_out: float, fee_usd: float
) -> tuple[float, float, float]:
    if usd_in <= 0:
        return 0.0, 0.0, 0.0
    fee_pct = max(0.0, fee_usd) / usd_in
    execution_cost_pct = (usd_in - usd_out) / usd_in
    cost_pct = max(fee_pct, max(0.0, execution_cost_pct))
    slippage_pct = max(0.0, cost_pct - fee_pct)
    return fee_pct, slippage_pct, cost_pct


def simulate_asset_swap(
    state: PoolState,
    asset: str,
    swap_size: float,
) -> SwapResult:
    """Simulate buying (``swap_size>0``) or selling (``swap_size<0``) ``asset``.

    Size is in human units of the risk asset. Quote asset is USDC.
    """
    if swap_size == 0:
        raise ValueError("swap_size must be non-zero")

    asset_is_token0, asset_decimals = _asset_side(state, asset)
    p0, p1 = token_usd_prices(state)
    asset_price = p0 if asset_is_token0 else p1
    quote_price = p1 if asset_is_token0 else p0
    if asset_price <= 0 or quote_price <= 0:
        raise ValueError(f"Cannot price tokens in pool {state.meta.address}")

    size_abs = abs(swap_size)
    amount_asset_raw = max(int(size_abs * (10**asset_decimals)), 1)
    buy = swap_size > 0

    if buy:
        # Exact-output of the asset: USDC in, asset out. zero_for_one iff asset is token1.
        zero_for_one = not asset_is_token0
        amount_in_raw, filled_out_raw, fee_raw, _ = _walk_swap(
            state, -amount_asset_raw, zero_for_one
        )
        if filled_out_raw < amount_asset_raw:
            raise ValueError(
                f"Pool {state.meta.address} cannot fill exact output "
                f"{amount_asset_raw} of {asset}; filled {filled_out_raw}"
            )
        amount_out_raw = amount_asset_raw
        dec_in = state.meta.decimals0 if zero_for_one else state.meta.decimals1
        price_in = p0 if zero_for_one else p1
        usd_in = (amount_in_raw / (10**dec_in)) * price_in
        usd_out = size_abs * asset_price
        fee_usd = (fee_raw / (10**dec_in)) * price_in
        amount_in_human = amount_in_raw / (10**dec_in)
        amount_out_human = size_abs
    else:
        # Exact-input of the asset: asset in, USDC out.
        zero_for_one = asset_is_token0
        _, amount_out_raw, fee_raw, _ = _walk_swap(
            state, amount_asset_raw, zero_for_one
        )
        amount_in_raw = amount_asset_raw
        dec_out = state.meta.decimals1 if zero_for_one else state.meta.decimals0
        price_out = p1 if zero_for_one else p0
        usd_in = size_abs * asset_price
        usd_out = (amount_out_raw / (10**dec_out)) * price_out
        fee_usd = (fee_raw / (10**asset_decimals)) * asset_price
        amount_in_human = size_abs
        amount_out_human = amount_out_raw / (10**dec_out)

    if amount_out_raw == 0:
        raise ValueError("Swap produced zero output")

    fee_pct, slippage_pct, cost_pct = _cost_breakdown(usd_in, usd_out, fee_usd)
    return SwapResult(
        amount_in=amount_in_human,
        amount_out=amount_out_human,
        amount_in_raw=amount_in_raw,
        amount_out_raw=amount_out_raw,
        fee_raw=fee_raw,
        fee_pct=fee_pct,
        slippage_pct=slippage_pct,
        cost_pct=cost_pct,
    )
