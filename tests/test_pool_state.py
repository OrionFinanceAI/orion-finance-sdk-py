"""Tests for Uniswap v3 pool snapshot fetch helpers."""

from unittest.mock import MagicMock, patch

from eth_abi import encode
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MIN_TICK,
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state import (
    PoolMeta,
    _compress_tick,
    _decompress_tick,
    _resolve_usdc_side,
    _token_symbol,
    enrich_pool_meta,
    fetch_pool_state,
    fetch_tick_liquidity_net,
    scan_initialized_ticks,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.rpc import TICK_INFO_TYPES

_SQRT = 1905189324021806733252815214030137


def _tick_info(net: int) -> bytes:
    return encode(TICK_INFO_TYPES, [0, net, 0, 0, 0, 0, 0, False])


def test_compress_tick_rounds_negative_non_multiples_down():
    assert _compress_tick(-11, 10) == -3
    assert _decompress_tick(-3, 10) == -30
    assert _compress_tick(10, 10) == 1
    assert _decompress_tick(1, 10) == 10


def test_scan_initialized_ticks_skips_none_and_zero_bitmap():
    spacing = 10
    min_word = _compress_tick(MIN_TICK, spacing) >> 8
    idx_word0 = 0 - min_word

    def fake_multicall(_w3, calls, _block, batch_size=500):
        results: list[bytes | None] = [None] * len(calls)
        results[idx_word0] = encode(["uint256"], [1])
        if idx_word0 + 1 < len(results):
            results[idx_word0 + 1] = encode(["uint256"], [0])
        return results

    with patch(
        "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.multicall_aggregate3",
        side_effect=fake_multicall,
    ):
        ticks = scan_initialized_ticks(MagicMock(), WETH_USDC_POOL, spacing, 1)
    assert ticks == [0]


def test_fetch_tick_liquidity_net_skips_bad_rows_and_zero_net():
    ticks = [10, 20, 30, 40]
    results = [
        None,
        b"\x00" * 32,
        _tick_info(0),
        _tick_info(-123),
    ]

    with patch(
        "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.multicall_aggregate3",
        return_value=results,
    ):
        net = fetch_tick_liquidity_net(MagicMock(), WETH_USDC_POOL, ticks, 1)
    assert net == {40: -123}


def test_resolve_usdc_side_token0_token1_and_neither():
    meta = PoolMeta(address=WETH_USDC_POOL, token0=USDC_ADDRESS, token1=WETH_ADDRESS)
    _resolve_usdc_side(meta)
    assert meta.stable_token == USDC_ADDRESS

    meta = PoolMeta(address=WETH_USDC_POOL, token0=WBTC_ADDRESS, token1=USDC_ADDRESS)
    _resolve_usdc_side(meta)
    assert meta.stable_token == USDC_ADDRESS

    meta = PoolMeta(address=WETH_USDC_POOL, token0=WBTC_ADDRESS, token1=WETH_ADDRESS)
    _resolve_usdc_side(meta)
    assert meta.stable_token is None


def test_token_symbol_falls_back_to_address_suffix():
    with patch(
        "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.erc20_symbol",
        side_effect=RuntimeError("no symbol"),
    ):
        assert _token_symbol(MagicMock(), WETH_ADDRESS, 1) == WETH_ADDRESS[-4:]


def test_enrich_pool_meta_fills_tokens_and_usdc_side():
    meta = PoolMeta(address=WETH_USDC_POOL)
    with (
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.pool_token",
            side_effect=[USDC_ADDRESS, WETH_ADDRESS],
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.pool_fee",
            return_value=500,
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.pool_tick_spacing",
            return_value=10,
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.erc20_decimals",
            side_effect=[6, 18],
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.erc20_symbol",
            side_effect=["USDC", "WETH"],
        ),
    ):
        out = enrich_pool_meta(MagicMock(), meta, 1)
    assert out.token0 == USDC_ADDRESS
    assert out.token1 == WETH_ADDRESS
    assert out.fee == 500
    assert out.tick_spacing == 10
    assert out.decimals0 == 6
    assert out.decimals1 == 18
    assert out.symbol0 == "USDC"
    assert out.symbol1 == "WETH"
    assert out.stable_token == USDC_ADDRESS


def test_fetch_pool_state_assembles_snapshot():
    meta = PoolMeta(address=WETH_USDC_POOL, tick_spacing=10, fee=500)
    with (
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.pool_slot0",
            return_value=(_SQRT, 100),
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.pool_liquidity",
            return_value=10**22,
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.scan_initialized_ticks",
            return_value=[90, 110],
        ),
        patch(
            "orion_finance_sdk_py.costs.venues.uniswap_v3.pool_state.fetch_tick_liquidity_net",
            return_value={90: 1, 110: -1},
        ),
    ):
        state = fetch_pool_state(MagicMock(), meta, 7)
    assert state.block_number == 7
    assert state.sqrt_price_x96 == _SQRT
    assert state.tick == 100
    assert state.liquidity == 10**22
    assert state.initialized_ticks == [90, 110]
    assert state.tick_liquidity_net == {90: 1, 110: -1}
