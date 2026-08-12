"""Public RPC defaults and health probing (mirrors install.sh cascade)."""

from __future__ import annotations

# Keep in sync with install.sh DEFAULT_RPC_* (Sepolia public endpoints).
DEFAULT_PUBLIC_RPC_URLS: tuple[str, ...] = (
    "https://1rpc.io/sepolia",
    "https://0xrpc.io/sep",
    "https://ethereum-sepolia-rpc.publicnode.com",
    "https://evm.stupidtech.net/v1/11155111",
)

_DEFAULT_RPC_CACHE: str | None = None


def clear_default_rpc_cache() -> None:
    """Clear the process-level cached default RPC URL (for tests)."""
    global _DEFAULT_RPC_CACHE
    _DEFAULT_RPC_CACHE = None


def rpc_works(url: str, timeout: float = 5.0) -> bool:
    """Return True if ``url`` answers ``eth_blockNumber`` within ``timeout`` seconds."""
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": timeout}))
        return bool(w3.is_connected())
    except Exception:
        return False


def pick_default_rpc(timeout: float = 5.0) -> str | None:
    """Probe default public RPCs in order; return the first that works (cached).

    Returns:
        A working RPC URL, or ``None`` if every default endpoint failed.
    """
    global _DEFAULT_RPC_CACHE
    if _DEFAULT_RPC_CACHE is not None:
        return _DEFAULT_RPC_CACHE

    for url in DEFAULT_PUBLIC_RPC_URLS:
        if rpc_works(url, timeout=timeout):
            _DEFAULT_RPC_CACHE = url
            return url
    return None
