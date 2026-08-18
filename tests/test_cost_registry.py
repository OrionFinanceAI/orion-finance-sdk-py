"""Tests for execution-cost symbol resolution."""

import pytest
from orion_finance_sdk_py.costs.registry import resolve_symbol
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    WBTC_ADDRESS,
    WBTC_USDC_POOL,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)


def test_resolve_ticker_weth():
    spec = resolve_symbol("WETH")
    assert spec.symbol == "WETH"
    assert spec.address.lower() == WETH_ADDRESS.lower()
    assert spec.pool.lower() == WETH_USDC_POOL.lower()
    assert spec.fee == 500


def test_resolve_ticker_wbtc():
    spec = resolve_symbol("WBTC")
    assert spec.symbol == "WBTC"
    assert spec.address.lower() == WBTC_ADDRESS.lower()
    assert spec.pool.lower() == WBTC_USDC_POOL.lower()
    assert spec.fee == 3000


def test_resolve_wbtc_mainnet_address():
    spec = resolve_symbol(WBTC_ADDRESS)
    assert spec.symbol == "WBTC"
    assert spec.pool.lower() == WBTC_USDC_POOL.lower()


def test_resolve_ticker_case_insensitive():
    assert resolve_symbol("weth").symbol == "WETH"
    assert resolve_symbol("XAUt").symbol == "XAUt"
    assert resolve_symbol("xaut").symbol == "XAUt"


def test_resolve_mainnet_address():
    spec = resolve_symbol(WETH_ADDRESS)
    assert spec.symbol == "WETH"


def test_reject_usdc():
    with pytest.raises(ValueError, match="quote asset"):
        resolve_symbol("USDC")
    with pytest.raises(ValueError, match="quote asset"):
        resolve_symbol("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")


def test_unknown_ticker():
    with pytest.raises(KeyError, match="Unknown symbol"):
        resolve_symbol("NOTACOIN")


def test_unknown_address_not_sepolia_guess():
    # A random mainnet-shaped address is not silently treated as a twin.
    with pytest.raises(KeyError, match="Unknown mainnet asset"):
        resolve_symbol("0x0000000000000000000000000000000000000001")
