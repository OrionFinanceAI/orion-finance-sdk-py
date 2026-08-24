"""Public RPC defaults, health probing, and chain-agnostic block lookup."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

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

_RPC_RETRY_ATTEMPTS = 5
_RPC_RETRY_BACKOFF = 0.25

T = TypeVar("T")


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


def _transient_rpc_errors() -> tuple[type[BaseException], ...]:
    """Errors that indicate a dropped / overloaded HTTP connection."""
    errors: list[type[BaseException]] = [ConnectionError, TimeoutError]
    try:
        import requests

        errors.append(requests.exceptions.RequestException)
    except ImportError:
        pass
    return tuple(errors)


def call_with_rpc_retry(
    fn: Callable[[], T],
    *,
    retries: int = _RPC_RETRY_ATTEMPTS,
    backoff_factor: float = _RPC_RETRY_BACKOFF,
) -> T:
    """Call ``fn``, retrying on transient transport failures.

    Does not retry application-level RPC / contract errors.
    """
    transient = _transient_rpc_errors()
    last_error: BaseException | None = None
    for attempt in range(retries):
        try:
            return fn()
        except transient as exc:
            last_error = exc
            if attempt >= retries - 1:
                break
            time.sleep(backoff_factor * (2**attempt))
    assert last_error is not None
    raise last_error


def make_http_provider(rpc_url: str, *, timeout: float = 60.0):
    """Build a ``Web3.HTTPProvider`` with timeout and connection-error retries."""
    import requests
    from web3 import Web3
    from web3.providers.rpc.utils import ExceptionRetryConfiguration

    return Web3.HTTPProvider(
        rpc_url,
        request_kwargs={"timeout": timeout},
        exception_retry_configuration=ExceptionRetryConfiguration(
            errors=(
                ConnectionError,
                requests.HTTPError,
                requests.Timeout,
            ),
            retries=_RPC_RETRY_ATTEMPTS,
            backoff_factor=_RPC_RETRY_BACKOFF,
        ),
    )


def get_block(w3: Web3, block_identifier):
    """``eth_getBlockByNumber`` with transient transport retries."""
    return call_with_rpc_retry(lambda: w3.eth.get_block(block_identifier))


def block_at_timestamp(
    w3: Web3,
    timestamp: int,
    *,
    lo: int | None = None,
    hi: int | None = None,
) -> int:
    """Return the latest block number whose timestamp is <= ``timestamp``.

    Optional ``lo`` / ``hi`` bound the binary search (inclusive). When omitted,
    the search uses genesis and the chain tip.
    """
    if timestamp < 0:
        raise ValueError("timestamp must be non-negative")

    if hi is None:
        hi = call_with_rpc_retry(lambda: w3.eth.block_number)
    hi_block = get_block(w3, hi)
    if timestamp >= hi_block["timestamp"]:
        return hi

    if lo is None:
        lo = 0
    lo_block = get_block(w3, lo)
    if timestamp < lo_block["timestamp"]:
        raise ValueError(
            f"timestamp {timestamp} is before the earliest block "
            f"({lo_block['timestamp']})"
            if lo == 0
            else (
                f"timestamp {timestamp} is before lower bound block {lo} "
                f"({lo_block['timestamp']})"
            )
        )

    while lo < hi:
        mid = (lo + hi + 1) // 2
        mid_ts = get_block(w3, mid)["timestamp"]
        if mid_ts <= timestamp:
            lo = mid
        else:
            hi = mid - 1
    return lo
