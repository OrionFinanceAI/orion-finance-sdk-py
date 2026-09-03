"""Custom-error decoding for Orion protocol reverts."""

from __future__ import annotations

from eth_utils import function_signature_to_4byte_selector

from .contracts import load_contract_abi

_SELECTOR_TO_NAME: dict[str, str] | None = None


def _error_selector_map() -> dict[str, str]:
    """Build 4-byte selector → error name from ErrorsLib (+ cached)."""
    global _SELECTOR_TO_NAME
    if _SELECTOR_TO_NAME is not None:
        return _SELECTOR_TO_NAME

    mapping: dict[str, str] = {}
    try:
        abi = load_contract_abi("ErrorsLib")
    except Exception:
        abi = []

    for item in abi:
        if item.get("type") != "error":
            continue
        name = item["name"]
        inputs = item.get("inputs") or []
        types = ",".join(inp["type"] for inp in inputs)
        sig = f"{name}({types})"
        selector = function_signature_to_4byte_selector(sig).hex()
        mapping[selector] = name

    _SELECTOR_TO_NAME = mapping
    return mapping


class ContractError(RuntimeError):
    """Raised when a transaction/call reverts with a known custom error."""

    def __init__(self, error_name: str, message: str | None = None):
        """Initialize with the onchain error name and optional message."""
        self.error_name = error_name
        super().__init__(message or error_name)


def decode_revert_data(data: bytes | str | None) -> str | None:
    """Return custom error name from revert data, or ``None`` if unknown."""
    if data is None:
        return None
    if isinstance(data, str):
        hex_str = data[2:] if data.startswith(("0x", "0X")) else data
        try:
            raw = bytes.fromhex(hex_str)
        except ValueError:
            return None
    else:
        raw = bytes(data)

    if len(raw) < 4:
        return None

    selector = raw[:4].hex()
    return _error_selector_map().get(selector)


def format_revert(
    data: bytes | str | None, fallback: str = "Transaction reverted"
) -> str:
    """Human-readable revert message including custom error name when known."""
    name = decode_revert_data(data)
    if name:
        return f"{fallback}: {name}"
    return fallback
