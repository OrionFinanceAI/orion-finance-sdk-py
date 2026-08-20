"""Resolve Orion universe tickers and mainnet addresses to Uniswap v3 pools."""

from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    ORION_FEE_TIERS,
    UNISWAP_V3_FACTORY,
    USDC_ADDRESS,
    WBTC_ADDRESS,
    WBTC_USDC_POOL,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.rpc import factory_get_pool
from orion_finance_sdk_py.erc20 import symbol as erc20_symbol
from orion_finance_sdk_py.types import ZERO_ADDRESS

XAUT_ADDRESS = "0x68749665FF8D2d112Fa859AA293F07A622782F38"
USDT_ADDRESS = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
DAI_ADDRESS = "0x6B175474E89094C44Da98b954EedeAC495271d0F"


@dataclass(frozen=True)
class VenueAsset:
    """Mainnet asset routed through a Uniswap v3 pool vs USDC."""

    symbol: str
    address: str
    pool: str
    fee: int


_ORION_UNISWAP_ASSETS: tuple[VenueAsset, ...] = (
    VenueAsset(
        "WETH",
        WETH_ADDRESS,
        WETH_USDC_POOL,
        500,
    ),
    VenueAsset(
        "WBTC",
        WBTC_ADDRESS,
        WBTC_USDC_POOL,
        3000,
    ),
    VenueAsset(
        "XAUt",
        XAUT_ADDRESS,
        "0x841ea2475A989eECCD27Fe39967c19CB097357A3",
        3000,
    ),
    VenueAsset(
        "USDT",
        USDT_ADDRESS,
        "0x3416cF6C7088c1442694EE5e59DDC1ec4aE07E4A",
        100,
    ),
    VenueAsset(
        "DAI",
        DAI_ADDRESS,
        "0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168",
        100,
    ),
)

_BY_SYMBOL: dict[str, VenueAsset] = {a.symbol.upper(): a for a in _ORION_UNISWAP_ASSETS}
_BY_ADDRESS: dict[str, VenueAsset] = {
    a.address.lower(): a for a in _ORION_UNISWAP_ASSETS
}


def looks_like_address(symbol: str) -> bool:
    """Return True if ``symbol`` looks like a 20-byte hex address."""
    return symbol.startswith("0x") and len(symbol) == 42


def resolve_symbol(symbol: str) -> VenueAsset:
    """Resolve a ticker or mainnet address to the Orion Uniswap v3 USDC pool.

    Does not accept Sepolia twin addresses. Unknown mainnet addresses can be
    resolved later via ``resolve_symbol_onchain``.
    """
    if not symbol or not str(symbol).strip():
        raise ValueError("symbol is required")
    raw = str(symbol).strip()

    if looks_like_address(raw):
        key = raw.lower()
        if key == USDC_ADDRESS.lower():
            raise ValueError("USDC is the quote asset; pass the risk-asset symbol")
        if key in _BY_ADDRESS:
            return _BY_ADDRESS[key]
        raise KeyError(
            f"Unknown mainnet asset {raw}. Pass a known ticker or use "
            "onchain factory lookup."
        )

    ticker = raw.upper()
    if ticker == "USDC":
        raise ValueError("USDC is the quote asset; pass the risk-asset symbol")
    if ticker in _BY_SYMBOL:
        return _BY_SYMBOL[ticker]
    raise KeyError(
        f"Unknown symbol {raw!r}. Use a ticker (e.g. WETH) or a mainnet address."
    )


def resolve_symbol_onchain(symbol: str, w3: Web3, block_number: int) -> VenueAsset:
    """Resolve ticker/address, falling back to Uniswap v3 factory ``getPool``."""
    try:
        return resolve_symbol(symbol)
    except KeyError:
        pass

    raw = str(symbol).strip()
    if not looks_like_address(raw):
        raise KeyError(
            f"Unknown symbol {raw!r}. Use a ticker (e.g. WETH) or a mainnet address."
        )

    token = Web3.to_checksum_address(raw)
    if token.lower() == USDC_ADDRESS.lower():
        raise ValueError("USDC is the quote asset; pass the risk-asset symbol")

    for fee in ORION_FEE_TIERS:
        pool = factory_get_pool(
            w3, UNISWAP_V3_FACTORY, token, USDC_ADDRESS, fee, block_number
        )
        if pool != ZERO_ADDRESS:
            try:
                ticker = erc20_symbol(w3, token, block=block_number)
            except Exception:
                ticker = token
            return VenueAsset(str(ticker), token, pool, fee)

    raise KeyError(f"No Uniswap v3 USDC pool found for {token}")
