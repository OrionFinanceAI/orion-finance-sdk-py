"""LP deposit/redeem event helpers (receipt parsing + optional log filters)."""

from __future__ import annotations

from typing import Any

from web3 import Web3
from web3.types import TxReceipt

from .contracts import load_contract_abi

_LP_EVENT_NAMES = (
    "DepositRequest",
    "DepositRequestCancelled",
    "RedeemRequest",
    "RedeemRequestCancelled",
)


def _vault_event_abis() -> list[dict[str, Any]]:
    """Return OrionVault ABI entries for LP queue events."""
    abi = load_contract_abi("OrionVault")
    return [
        item
        for item in abi
        if item.get("type") == "event" and item.get("name") in _LP_EVENT_NAMES
    ]


def parse_lp_events_from_receipt(
    w3: Web3,
    receipt: TxReceipt,
    vault_address: str | None = None,
) -> list[dict[str, Any]]:
    """Decode LP queue events from a transaction receipt.

    Args:
        w3: Web3 instance.
        receipt: Transaction receipt.
        vault_address: Optional vault address filter (checksummed comparison).

    Returns:
        List of ``{"event", "args", "address", "logIndex"}`` dicts.
    """
    contract = w3.eth.contract(abi=_vault_event_abis())
    vault_filter = (
        Web3.to_checksum_address(vault_address) if vault_address else None
    )
    decoded: list[dict[str, Any]] = []
    for log in receipt.get("logs", []):
        if vault_filter and Web3.to_checksum_address(log["address"]) != vault_filter:
            continue
        for event_abi in _vault_event_abis():
            event = contract.events[event_abi["name"]]()
            try:
                parsed = event.process_log(log)
            except Exception:
                continue
            decoded.append(
                {
                    "event": parsed["event"],
                    "args": dict(parsed["args"]),
                    "address": Web3.to_checksum_address(parsed["address"]),
                    "logIndex": parsed.get("logIndex"),
                }
            )
            break
    return decoded


def get_lp_events(
    w3: Web3,
    vault_address: str,
    *,
    from_block: int | str = 0,
    to_block: int | str = "latest",
    event_names: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Fetch historical LP queue events for a vault via ``eth_getLogs``.

    Consumers can reconcile per-user pending amounts locally from these events.
    Public RPCs may rate-limit large ranges — prefer a dedicated ``RPC_URL``.
    """
    names = event_names or _LP_EVENT_NAMES
    vault = Web3.to_checksum_address(vault_address)
    contract = w3.eth.contract(address=vault, abi=_vault_event_abis())
    results: list[dict[str, Any]] = []
    for name in names:
        event = getattr(contract.events, name)
        logs = event.get_logs(from_block=from_block, to_block=to_block)
        for parsed in logs:
            results.append(
                {
                    "event": parsed["event"],
                    "args": dict(parsed["args"]),
                    "address": Web3.to_checksum_address(parsed["address"]),
                    "blockNumber": parsed.get("blockNumber"),
                    "transactionHash": (
                        parsed["transactionHash"].hex()
                        if parsed.get("transactionHash") is not None
                        else None
                    ),
                    "logIndex": parsed.get("logIndex"),
                }
            )
    results.sort(
        key=lambda item: (
            item.get("blockNumber") or 0,
            item.get("logIndex") or 0,
        )
    )
    return results
