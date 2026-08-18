"""Tests for ExecutionCostEstimator.get_cost with a fixture pool snapshot."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.costs import estimator as estimator_mod
from orion_finance_sdk_py.costs.estimator import ExecutionCostEstimator, get_cost
from orion_finance_sdk_py.costs.registry import VenueAsset, resolve_symbol
from orion_finance_sdk_py.costs.types import ExecutionCost
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WBTC_USDC_POOL,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)

UNKNOWN_ADDR = "0x0000000000000000000000000000000000000001"
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


def _estimator(*, at: datetime | None = None) -> ExecutionCostEstimator:
    when = at or datetime.now(timezone.utc)
    est = ExecutionCostEstimator(block_number=1)
    est.preload_uniswap_state("WETH", _weth_usdc_state())
    est.preload_uniswap_state("WBTC", _wbtc_usdc_state())
    w3 = MagicMock()
    w3.eth.get_block.return_value = {"timestamp": int(when.timestamp())}
    est._w3 = w3
    return est


def test_pool_state_from_json_ignores_unknown_meta_keys():
    payload = _weth_usdc_state().to_json()
    payload["meta"]["positive_usd_zero_for_one"] = True
    state = PoolState.from_json(payload)
    assert not hasattr(state.meta, "positive_usd_zero_for_one")
    assert state.meta.stable_token == USDC_ADDRESS


def test_preload_rejects_snapshot_that_does_not_match_registry_pool():
    est = ExecutionCostEstimator(block_number=1)
    with pytest.raises(ValueError, match="does not match WETH"):
        est.preload_uniswap_state("WETH", _wbtc_usdc_state())


def test_buy_and_sell_have_positive_cost():
    est = _estimator(at=datetime(2026, 8, 1, tzinfo=timezone.utc))
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
    before = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cost = est.get_cost("WETH", 0.01)
    after = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert cost.timestamp in {before, after}


def test_block_override_uses_header_date_not_caller_timestamp():
    est = _estimator(at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    cost = est.get_cost("WETH", 0.01, timestamp="2026-07-01")
    assert cost.timestamp == "2026-08-01"


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
    with pytest.raises(ValueError, match="non-zero"):
        est.get_cost("WETH", float("nan"))
    with pytest.raises(ValueError, match="non-zero"):
        est.get_cost("WETH", float("inf"))


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


def test_web3_uses_public_mainnet_rpc_when_env_unset(monkeypatch):
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    est = ExecutionCostEstimator()
    fake = MagicMock()
    with (
        patch.object(
            estimator_mod,
            "pick_default_mainnet_rpc",
            return_value="https://public.example",
        ) as picker,
        patch.object(estimator_mod, "connect_mainnet", return_value=fake) as mocked,
    ):
        assert est._web3() is fake
        assert est._web3() is fake
    picker.assert_called_once()
    mocked.assert_called_once_with("https://public.example")
    assert est._rpc_url == "https://public.example"


def test_web3_errors_when_public_mainnet_rpcs_fail(monkeypatch):
    monkeypatch.delenv("MAINNET_RPC_URL", raising=False)
    est = ExecutionCostEstimator()
    with patch.object(estimator_mod, "pick_default_mainnet_rpc", return_value=None):
        with pytest.raises(RuntimeError, match="public Ethereum mainnet RPC"):
            est._web3()


def test_web3_connects_and_caches():
    est = ExecutionCostEstimator(rpc_url="https://example.invalid")
    fake = MagicMock()
    with (
        patch.object(estimator_mod, "pick_default_mainnet_rpc") as picker,
        patch.object(estimator_mod, "connect_mainnet", return_value=fake) as mocked,
    ):
        assert est._web3() is fake
        assert est._web3() is fake
    picker.assert_not_called()
    mocked.assert_called_once_with("https://example.invalid")


def test_netting_eta_must_be_unit_interval():
    est = _estimator()
    with pytest.raises(ValueError, match="netting_eta"):
        est.get_cost("WETH", 0.01, netting_eta=-0.1)
    with pytest.raises(ValueError, match="netting_eta"):
        est.get_cost("WETH", 0.01, netting_eta=1.1)


def test_module_get_cost_wrapper():
    est = _estimator()
    previous = estimator_mod._DEFAULT_ESTIMATOR
    estimator_mod._DEFAULT_ESTIMATOR = est
    try:
        cost = get_cost("WETH", 0.01, timestamp="2026-08-01")
        assert cost.symbol == "WETH"
        assert cost.cost_pct > 0
    finally:
        estimator_mod._DEFAULT_ESTIMATOR = previous


def test_module_get_cost_creates_default_estimator(monkeypatch):
    previous = estimator_mod._DEFAULT_ESTIMATOR
    estimator_mod._DEFAULT_ESTIMATOR = None

    def _fake_get_cost(self, *args, **kwargs):
        return MagicMock(symbol="WETH")

    monkeypatch.setattr(ExecutionCostEstimator, "get_cost", _fake_get_cost)
    try:
        out = get_cost("WETH", 0.01)
        assert out.symbol == "WETH"
        assert estimator_mod._DEFAULT_ESTIMATOR is not None
    finally:
        estimator_mod._DEFAULT_ESTIMATOR = previous


def test_preload_unknown_symbol_on_usdc_pair():
    est = ExecutionCostEstimator(block_number=1)
    est.preload_uniswap_state("FAKE", _weth_usdc_state())
    assert est._extra_assets["WETH"].symbol == "WETH"
    est.preload_uniswap_state("ALSOFAKE", _wbtc_usdc_state())
    assert est._extra_assets["WBTC"].symbol == "WBTC"


def test_preload_unknown_address_uses_checksum_address():
    est = ExecutionCostEstimator(block_number=1)
    est.preload_uniswap_state(UNKNOWN_ADDR, _weth_usdc_state())
    spec = est._extra_assets[UNKNOWN_ADDR.lower()]
    assert spec.address == UNKNOWN_ADDR
    assert spec.symbol == "WETH"


def test_preload_rejects_non_usdc_pair():
    est = ExecutionCostEstimator(block_number=1)
    meta = PoolMeta(
        address=WETH_USDC_POOL,
        token0=WBTC_ADDRESS,
        token1=WETH_ADDRESS,
        fee=500,
        decimals0=8,
        decimals1=18,
        tick_spacing=10,
        symbol0="WBTC",
        symbol1="WETH",
    )
    state = PoolState(
        meta=meta,
        block_number=1,
        sqrt_price_x96=_SQRT_PRICE_X96,
        tick=0,
        liquidity=10**22,
    )
    with pytest.raises(ValueError, match="not an USDC pair"):
        est.preload_uniswap_state("FOO", state)


def test_snapshot_fetches_caches_and_rejects_zero_liquidity():
    est = ExecutionCostEstimator(rpc_url="https://example.invalid", block_number=1)
    est._w3 = MagicMock()
    spec = resolve_symbol("WETH")
    live = _weth_usdc_state()
    calls = {"n": 0}

    def _fetch(_w3, _meta, _block):
        calls["n"] += 1
        return live

    with (
        patch.object(estimator_mod, "enrich_pool_meta", lambda w3, meta, block: meta),
        patch.object(estimator_mod, "fetch_pool_state", _fetch),
    ):
        first = est._snapshot(spec, 1)
        second = est._snapshot(spec, 1)
    assert first is live
    assert second is live
    assert calls["n"] == 1

    empty = _weth_usdc_state()
    empty.liquidity = 0
    est2 = ExecutionCostEstimator(rpc_url="https://example.invalid", block_number=1)
    est2._w3 = MagicMock()
    with (
        patch.object(estimator_mod, "enrich_pool_meta", lambda w3, meta, block: meta),
        patch.object(estimator_mod, "fetch_pool_state", lambda w3, meta, block: empty),
    ):
        with pytest.raises(RuntimeError, match="zero liquidity"):
            est2._snapshot(spec, 1)


def test_resolve_asset_unknown_address_uses_onchain():
    est = _estimator()
    fake = VenueAsset("FOO", UNKNOWN_ADDR, WETH_USDC_POOL, 500)
    with patch.object(
        estimator_mod, "resolve_symbol_onchain", return_value=fake
    ) as mocked:
        spec = est._resolve_asset(UNKNOWN_ADDR, 1)
    assert spec is fake
    mocked.assert_called_once()


def test_resolve_block_without_override_uses_timestamp_lookup():
    est = ExecutionCostEstimator(rpc_url="https://example.invalid")
    est._w3 = MagicMock()
    with patch.object(estimator_mod, "block_at_timestamp", return_value=99) as mocked:
        assert est._resolve_block(1_700_000_000) == 99
    mocked.assert_called_once()


def test_resolve_block_honors_override():
    est = ExecutionCostEstimator(block_number=42)
    assert est._resolve_block(1_700_000_000) == 42


def test_get_cost_without_block_override_looks_up_timestamp():
    est = ExecutionCostEstimator()
    est.preload_uniswap_state("WETH", _weth_usdc_state())
    est._w3 = MagicMock()
    with patch.object(estimator_mod, "block_at_timestamp", return_value=1):
        cost = est.get_cost("WETH", 0.01, timestamp="2026-08-01")
    assert cost.timestamp == "2026-08-01"
    assert cost.cost_pct > 0


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("MAINNET_RPC_URL"), reason="MAINNET_RPC_URL not set"
)
def test_live_mainnet_optional():
    est = ExecutionCostEstimator()
    cost = est.get_cost("WETH", 0.01)
    assert cost.cost_pct >= 0
    assert cost.amount_out > 0
