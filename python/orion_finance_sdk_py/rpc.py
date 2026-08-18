"""Public RPC defaults, health probing, and chain-agnostic block lookup."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web3 import Web3

# Keep in sync with install.sh DEFAULT_RPC_* (Sepolia public endpoints).
DEFAULT_PUBLIC_RPC_URLS: tuple[str, ...] = (
    "https://1rpc.io/sepolia",
    "https://0xrpc.io/sep",
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://evm.stupidtech.net/v1/11155111",
)

# Public Ethereum mainnet endpoints for read-only cost estimates.
DEFAULT_PUBLIC_MAINNET_RPC_URLS: tuple[str, ...] = (
    "https://ethereum-rpc.publicnode.com",
    "https://eth-mainnet.g.alchemy.com/public",
    "https://public.1rpc.io/eth",
    "https://eth.drpc.org/",
)

_DEFAULT_RPC_CACHE: str | None = None
_DEFAULT_MAINNET_RPC_CACHE: str | None = None


def clear_default_rpc_cache() -> None:
    """Clear process-level cached default RPC URLs (for tests)."""
    global _DEFAULT_RPC_CACHE, _DEFAULT_MAINNET_RPC_CACHE
    _DEFAULT_RPC_CACHE = None
    _DEFAULT_MAINNET_RPC_CACHE = None


def rpc_works(url: str, timeout: float = 5.0) -> bool:
    """Return True if ``url`` answers ``eth_blockNumber`` within ``timeout`` seconds."""
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": timeout}))
        return bool(w3.is_connected())
    except Exception:
        return False


def _pick_first_working(
    urls: tuple[str, ...], cache: str | None, timeout: float
) -> tuple[str | None, str | None]:
    """Return ``(chosen_url, updated_cache)``. ``cache`` is reused when set."""
    if cache is not None:
        return cache, cache
    for url in urls:
        if rpc_works(url, timeout=timeout):
            return url, url
    return None, None


def pick_default_rpc(timeout: float = 5.0) -> str | None:
    """Probe default public Sepolia RPCs in order; return the first that works (cached).

    Returns:
        A working RPC URL, or ``None`` if every default endpoint failed.
    """
    global _DEFAULT_RPC_CACHE
    url, _DEFAULT_RPC_CACHE = _pick_first_working(
        DEFAULT_PUBLIC_RPC_URLS, _DEFAULT_RPC_CACHE, timeout
    )
    return url


def pick_default_mainnet_rpc(timeout: float = 5.0) -> str | None:
    """Probe default public mainnet RPCs in order; return the first that works (cached).

    Returns:
        A working RPC URL, or ``None`` if every default endpoint failed.
    """
    global _DEFAULT_MAINNET_RPC_CACHE
    url, _DEFAULT_MAINNET_RPC_CACHE = _pick_first_working(
        DEFAULT_PUBLIC_MAINNET_RPC_URLS, _DEFAULT_MAINNET_RPC_CACHE, timeout
    )
    return url


def block_at_timestamp(w3: Web3, timestamp: int) -> int:
    """Return the latest block number whose timestamp is <= ``timestamp``."""
    if timestamp < 0:
        raise ValueError("timestamp must be non-negative")

    latest = w3.eth.block_number
    latest_block = w3.eth.get_block(latest)
    if timestamp >= latest_block["timestamp"]:
        return latest

    earliest = 0
    earliest_block = w3.eth.get_block(earliest)
    if timestamp < earliest_block["timestamp"]:
        raise ValueError(
            f"timestamp {timestamp} is before the earliest block "
            f"({earliest_block['timestamp']})"
        )

    lo, hi = earliest, latest
    while lo < hi:
        mid = (lo + hi + 1) // 2
        mid_ts = w3.eth.get_block(mid)["timestamp"]
        if mid_ts <= timestamp:
            lo = mid
        else:
            hi = mid - 1
    return lo
