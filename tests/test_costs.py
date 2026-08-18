"""Tests for ExecutionCostEstimator.get_cost with a fixture pool snapshot."""

from __future__ import annotations

import os

import pytest
from orion_finance_sdk_py.costs.estimator import ExecutionCostEstimator
from orion_finance_sdk_py.costs.types import ExecutionCost
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WBTC_USDC_POOL,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state import PoolMeta, PoolState
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.tick_math import (
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
)

# USDC/WETH 0.05% pool mid from protocol-costs pricing tests.
_SQRT_PRICE_X96 = 1905189324021806733252815214030137
# WBTC is token0 vs USDC; tick ~69060 ≈ $100k.
_WBTC_TICK = 69060
_WBTC_SQRT_PRICE_X96 = get_sqrt_ratio_at_tick(_WBTC_TICK)


def _weth_usdc_state() -> PoolState:
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
    return PoolState(
        meta=meta,
        block_number=1,
        sqrt_price_x96=_SQRT_PRICE_X96,
        tick=get_tick_at_sqrt_ratio(_SQRT_PRICE_X96),
        liquidity=10**22,
        tick_liquidity_net={},
        initialized_ticks=[],
    )


def _wbtc_usdc_state() -> PoolState:
    meta = PoolMeta(
        address=WBTC_USDC_POOL,
        token0=WBTC_ADDRESS,
        token1=USDC_ADDRESS,
        fee=3000,
        decimals0=8,
        decimals1=6,
        tick_spacing=60,
        stable_token=USDC_ADDRESS,
        symbol0="WBTC",
        symbol1="USDC",
    )
    return PoolState(
        meta=meta,
        block_number=1,
        sqrt_price_x96=_WBTC_SQRT_PRICE_X96,
        tick=_WBTC_TICK,
        liquidity=10**22,
        tick_liquidity_net={},
        initialized_ticks=[],
    )


def _estimator() -> ExecutionCostEstimator:
    est = ExecutionCostEstimator(block_number=1)
    est.preload_uniswap_state("WETH", _weth_usdc_state())
    est.preload_uniswap_state("WBTC", _wbtc_usdc_state())
    return est


def test_pool_state_from_json_ignores_unknown_meta_keys():
    payload = _weth_usdc_state().to_json()
    payload["meta"]["positive_usd_zero_for_one"] = True
    state = PoolState.from_json(payload)
    assert not hasattr(state.meta, "positive_usd_zero_for_one")
    assert state.meta.stable_token == USDC_ADDRESS


def test_buy_and_sell_have_positive_cost():
    est = _estimator()
    buy = est.get_cost("WETH", 0.01, timestamp="2026-08-01")
    sell = est.get_cost("WETH", -0.01, timestamp="2026-08-01")
    assert isinstance(buy, ExecutionCost)
    assert buy.cost_pct > 0
    assert sell.cost_pct > 0
    assert buy.fee_pct > 0
    assert sell.fee_pct > 0
    assert buy.signed_size == 0.01
    assert buy.swap_size == pytest.approx(0.01)
    assert sell.swap_size == pytest.approx(-0.01)
    assert buy.timestamp == "2026-08-01"
    assert not hasattr(buy, "pool")
    assert not hasattr(buy, "fee_tier")


def test_default_timestamp_is_today():
    est = _estimator()
    cost = est.get_cost("WETH", 0.01)
    assert len(cost.timestamp) == 10
    assert cost.timestamp[4] == "-"


def test_mainnet_address_symbol():
    est = _estimator()
    cost = est.get_cost(WETH_ADDRESS, 0.01, timestamp="2026-08-01")
    assert cost.symbol == "WETH"


def test_wbtc_buy_and_sell():
    est = _estimator()
    buy = est.get_cost("WBTC", 0.01, timestamp="2026-08-01")
    sell = est.get_cost(WBTC_ADDRESS, -0.01, timestamp="2026-08-01")
    assert buy.symbol == "WBTC"
    assert sell.symbol == "WBTC"
    assert buy.cost_pct > 0
    assert sell.cost_pct > 0
    assert buy.amount_out == pytest.approx(0.01)


def test_zero_size_rejected():
    est = _estimator()
    with pytest.raises(ValueError, match="non-zero"):
        est.get_cost("WETH", 0)


def test_unknown_symbol():
    est = _estimator()
    with pytest.raises(KeyError):
        est.get_cost("NOTACOIN", 1.0, timestamp="2026-08-01")


def test_netting_reduces_swap_size_not_cost_linearly():
    est = _estimator()
    nominal = 0.02
    eta = 0.5
    netted = est.get_cost("WETH", nominal, timestamp="2026-08-01", netting_eta=eta)
    direct = est.get_cost(
        "WETH", (1.0 - eta) * nominal, timestamp="2026-08-01", netting_eta=0.0
    )
    unnetted = est.get_cost("WETH", nominal, timestamp="2026-08-01")

    assert netted.swap_size == pytest.approx((1.0 - eta) * nominal)
    assert netted.cost_pct == pytest.approx(direct.cost_pct, rel=1e-9)
    assert netted.cost_pct != pytest.approx(unnetted.cost_pct * (1.0 - eta))


def test_full_netting_is_zero_cost():
    est = _estimator()
    cost = est.get_cost("WETH", 1.0, timestamp="2026-08-01", netting_eta=1.0)
    assert cost.swap_size == 0.0
    assert cost.cost_pct == 0.0
    assert cost.amount_in == 0.0


def test_unsupported_venue():
    est = _estimator()
    with pytest.raises(ValueError, match="Unsupported venue"):
        est.get_cost("WETH", 0.01, venue="bebop_rfq")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("MAINNET_RPC_URL"), reason="MAINNET_RPC_URL not set"
)
def test_live_mainnet_optional():
    est = ExecutionCostEstimator()
    cost = est.get_cost("WETH", 0.01)
    assert cost.cost_pct >= 0
    assert cost.amount_out > 0
