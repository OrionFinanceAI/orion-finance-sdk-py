"""Chain-specific OrionConfig env. No defaults, no ORION_CONFIG_ADDRESS."""

from __future__ import annotations

import os
from collections.abc import Mapping

from web3 import Web3

from .types import ZERO_ADDRESS

SEPOLIA_ORION_CONFIG = "0xbDe3025d08681a02a1c6cf70375baBe2152DD06f"
SEPOLIA_CHAIN_ID = 11155111
MAINNET_CHAIN_ID = 1

SUPPORTED_CHAIN_NAMES: dict[str, int] = {
    "sepolia": SEPOLIA_CHAIN_ID,
    "mainnet": MAINNET_CHAIN_ID,
}
CHAIN_ID_TO_NAME: dict[int, str] = {cid: name for name, cid in SUPPORTED_CHAIN_NAMES.items()}


def parse_chain_name(name: str) -> int:
    """Map ``sepolia`` / ``mainnet`` to chain id. Raises ``ValueError`` if unknown."""
    key = name.strip().lower()
    if key not in SUPPORTED_CHAIN_NAMES:
        raise ValueError(f"Unsupported chain: {name!r}. Use sepolia or mainnet.")
    return SUPPORTED_CHAIN_NAMES[key]


def has_explicit_chain_selection(
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return True when ``CHAIN`` or ``CHAIN_ID`` is set in the environment."""
    source: Mapping[str, str | None] = env if env is not None else os.environ
    if (source.get("CHAIN") or "").strip():
        return True
    return bool((source.get("CHAIN_ID") or "").strip())


def resolve_ambiguous_write_rpc_url(
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Pick the sole configured write RPC when ``CHAIN`` / ``CHAIN_ID`` is unset.

    Raises ``ValueError`` when both chain-scoped RPC URLs are set.
    """
    source: Mapping[str, str | None] = env if env is not None else os.environ
    mainnet = (source.get("MAINNET_RPC_URL") or "").strip()
    sepolia = (source.get("SEPOLIA_RPC_URL") or "").strip()
    if mainnet and sepolia:
        raise ValueError(
            "CHAIN or CHAIN_ID is required when both MAINNET_RPC_URL and "
            "SEPOLIA_RPC_URL are set."
        )
    if mainnet:
        return mainnet
    if sepolia:
        return sepolia
    return None


def resolve_active_chain_id(
    chain_cli: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Resolve active chain id.

    Priority: ``--chain`` / ``chain_cli`` → ``CHAIN`` env → ``CHAIN_ID`` env → Sepolia.
    """
    source: Mapping[str, str | None] = env if env is not None else os.environ
    if chain_cli is not None and str(chain_cli).strip():
        return parse_chain_name(str(chain_cli))

    chain_env = (source.get("CHAIN") or "").strip()
    if chain_env:
        return parse_chain_name(chain_env)

    raw_id = (source.get("CHAIN_ID") or "").strip()
    if not raw_id:
        return SEPOLIA_CHAIN_ID
    try:
        return int(raw_id)
    except ValueError as exc:
        raise ValueError(f"Invalid CHAIN_ID: {raw_id}") from exc


def apply_chain_selection(chain_cli: str | None = None) -> int:
    """Set ``CHAIN_ID`` (and ``CHAIN`` when known) in ``os.environ`` for the process."""
    chain_id = resolve_active_chain_id(chain_cli)
    os.environ["CHAIN_ID"] = str(chain_id)
    name = CHAIN_ID_TO_NAME.get(chain_id)
    if name:
        os.environ["CHAIN"] = name
    return chain_id


def write_rpc_env_name(
    chain_id: int | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Env var for the write/keeper RPC on the active chain. No bare ``RPC_URL``."""
    source: Mapping[str, str | None] = env if env is not None else os.environ
    if chain_id is None:
        chain_id = resolve_active_chain_id(env=source)
    return "MAINNET_RPC_URL" if chain_id == MAINNET_CHAIN_ID else "SEPOLIA_RPC_URL"


def resolve_configured_write_rpc_url(
    chain_id: int | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Return chain-scoped RPC from env, or ``None`` if unset.

    Ignores bare ``RPC_URL``. Mainnet → ``MAINNET_RPC_URL``; everything else
    (Sepolia / local forks) → ``SEPOLIA_RPC_URL``.
    """
    source: Mapping[str, str | None] = env if env is not None else os.environ
    if chain_id is None:
        chain_id = resolve_active_chain_id(env=source)
    name = write_rpc_env_name(chain_id, source)
    raw = (source.get(name) or "").strip()
    return raw or None


def resolve_orion_config_address(
    chain_id: int | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return checksummed OrionConfig for the active chain.

    ``CHAIN_ID=1`` / ``CHAIN=mainnet`` reads ``MAINNET_ORION_CONFIG_ADDRESS``;
    anything else (including unset, Sepolia, and local forks) reads
    ``SEPOLIA_ORION_CONFIG_ADDRESS``.
    """
    source: Mapping[str, str | None] = env if env is not None else os.environ
    if chain_id is None:
        chain_id = resolve_active_chain_id(env=source)

    is_mainnet = chain_id == MAINNET_CHAIN_ID
    name = "MAINNET_ORION_CONFIG_ADDRESS" if is_mainnet else "SEPOLIA_ORION_CONFIG_ADDRESS"
    network = "mainnet" if is_mainnet else "sepolia"
    raw = (source.get(name) or "").strip()
    if not raw:
        raise ValueError(f"{name} is required for network {network}")

    try:
        addr = Web3.to_checksum_address(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} is not a valid address") from exc

    if addr.lower() == ZERO_ADDRESS.lower():
        raise ValueError(f"{name} must not be the zero address")

    if is_mainnet and addr.lower() == SEPOLIA_ORION_CONFIG.lower():
        raise ValueError(f"{name} must not be the Sepolia OrionConfig")

    return addr
