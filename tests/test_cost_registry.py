"""Tests for execution-cost symbol resolution."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.costs.registry import resolve_symbol, resolve_symbol_onchain
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WBTC_USDC_POOL,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.types import ZERO_ADDRESS

UNKNOWN = "0x0000000000000000000000000000000000000001"
UNKNOWN_POOL = "0x1111111111111111111111111111111111111111"


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
        resolve_symbol(UNKNOWN)


def test_resolve_symbol_requires_value():
    with pytest.raises(ValueError, match="symbol is required"):
        resolve_symbol("")
    with pytest.raises(ValueError, match="symbol is required"):
        resolve_symbol("   ")


def test_resolve_symbol_onchain_uses_static_map_for_known_ticker():
    w3 = MagicMock()
    spec = resolve_symbol_onchain("WETH", w3, 1)
    assert spec.symbol == "WETH"
    w3.eth.call.assert_not_called()


def test_resolve_symbol_onchain_unknown_ticker():
    with pytest.raises(KeyError, match="Unknown symbol"):
        resolve_symbol_onchain("NOTACOIN", MagicMock(), 1)


def test_resolve_symbol_onchain_factory_hit():
    w3 = MagicMock()
    with (
        patch(
            "orion_finance_sdk_py.costs.registry.factory_get_pool",
            return_value=UNKNOWN_POOL,
        ) as factory,
        patch(
            "orion_finance_sdk_py.costs.registry.erc20_symbol",
            return_value="FOO",
        ),
    ):
        spec = resolve_symbol_onchain(UNKNOWN, w3, 12)
    assert spec.symbol == "FOO"
    assert spec.address == UNKNOWN
    assert spec.pool == UNKNOWN_POOL
    assert spec.fee == 500
    factory.assert_called_once()


def test_resolve_symbol_onchain_symbol_lookup_falls_back_to_address():
    w3 = MagicMock()
    with (
        patch(
            "orion_finance_sdk_py.costs.registry.factory_get_pool",
            return_value=UNKNOWN_POOL,
        ),
        patch(
            "orion_finance_sdk_py.costs.registry.erc20_symbol",
            side_effect=RuntimeError("no symbol"),
        ),
    ):
        spec = resolve_symbol_onchain(UNKNOWN, w3, 1)
    assert spec.symbol == UNKNOWN


def test_resolve_symbol_onchain_no_pool():
    w3 = MagicMock()
    with patch(
        "orion_finance_sdk_py.costs.registry.factory_get_pool",
        return_value=ZERO_ADDRESS,
    ):
        with pytest.raises(KeyError, match="No Uniswap v3 USDC pool"):
            resolve_symbol_onchain(UNKNOWN, w3, 1)


def test_resolve_symbol_onchain_rejects_usdc():
    with pytest.raises(ValueError, match="quote asset"):
        resolve_symbol_onchain("USDC", MagicMock(), 1)
    with pytest.raises(ValueError, match="quote asset"):
        resolve_symbol_onchain(USDC_ADDRESS, MagicMock(), 1)
