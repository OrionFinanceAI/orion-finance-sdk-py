"""Tests for Uniswap v3 swap simulation edge paths."""

from __future__ import annotations

import pytest
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state import PoolMeta, PoolState
from orion_finance_sdk_py.costs.venues.uniswap_v3.simulator import (
    _add_liquidity_delta,
    _walk_swap,
    simulate_asset_swap,
    token_usd_prices,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.tick_math import (
    get_tick_at_sqrt_ratio,
)

_SQRT_PRICE_X96 = 1905189324021806733252815214030137


def _weth_usdc_state(**overrides) -> PoolState:
    meta = PoolMeta(
        address=WETH_USDC_POOL,
        token0=USDC_ADDRESS,
        token1=WETH_ADDRESS,
        fee=500,
        decimals0=6,
        decimals1=18,
        tick_spacing=10,
        stable_token=USDC_ADDRESS,
        symbol0="USDC",
        symbol1="WETH",
    )
    tick = get_tick_at_sqrt_ratio(_SQRT_PRICE_X96)
    kwargs = {
        "meta": meta,
        "block_number": 1,
        "sqrt_price_x96": _SQRT_PRICE_X96,
        "tick": tick,
        "liquidity": 10**22,
        "tick_liquidity_net": {},
        "initialized_ticks": [],
    }
    kwargs.update(overrides)
    return PoolState(**kwargs)


def test_simulate_rejects_zero_size():
    with pytest.raises(ValueError, match="non-zero"):
        simulate_asset_swap(_weth_usdc_state(), WETH_ADDRESS, 0)


def test_simulate_rejects_asset_not_in_pool():
    with pytest.raises(ValueError, match="is not in pool"):
        simulate_asset_swap(_weth_usdc_state(), WBTC_ADDRESS, 0.01)


def test_token_usd_prices_requires_usdc_pair():
    state = _weth_usdc_state()
    state.meta.stable_token = None
    with pytest.raises(ValueError, match="not a USDC pair"):
        token_usd_prices(state)


def test_walk_swap_zero_remaining_is_noop():
    state = _weth_usdc_state()
    amount_in, amount_out, fee, sqrt = _walk_swap(state, 0, True)
    assert amount_in == 0
    assert amount_out == 0
    assert fee == 0
    assert sqrt == state.sqrt_price_x96


def test_add_liquidity_delta_underflow():
    with pytest.raises(ValueError, match="liquidity underflow"):
        _add_liquidity_delta(10, -11)


def test_swap_crosses_initialized_tick():
    state = _weth_usdc_state()
    tick_below = state.tick - 10
    state.initialized_ticks = [tick_below]
    state.tick_liquidity_net = {tick_below: 10**18}
    result = simulate_asset_swap(state, WETH_ADDRESS, 50.0)
    assert result.amount_out == pytest.approx(50.0)
    assert result.cost_pct > 0


def test_exact_output_unfillable_raises():
    state = _weth_usdc_state(liquidity=1)
    with pytest.raises(ValueError, match="cannot fill exact output"):
        simulate_asset_swap(state, WETH_ADDRESS, 1_000_000.0)
