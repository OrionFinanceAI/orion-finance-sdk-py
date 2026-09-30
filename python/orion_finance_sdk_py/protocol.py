"""Protocol phase / idle helpers for async epoch UX."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

# Matches onchain ``ILiquidityOrchestrator.LiquidityUpkeepPhase``.
PHASE_NAMES: dict[int, str] = {
    0: "Idle",
    1: "StateCommitment",
    2: "SellingLeg",
    3: "BuyingLeg",
    4: "ProcessVaultOperations",
}


def phase_name(phase: int) -> str:
    """Return the human label for an LO phase enum value."""
    return PHASE_NAMES.get(int(phase), f"Unknown({phase})")


def protocol_status() -> dict[str, Any]:
    """Snapshot idle flag, phase, and epoch timing for UX / errors."""
    from .contracts import LiquidityOrchestrator, OrionConfig

    config = OrionConfig()
    lo = LiquidityOrchestrator()
    phase = int(lo.current_phase)
    return {
        "is_system_idle": bool(config.is_system_idle()),
        "phase": phase,
        "phase_name": phase_name(phase),
        "epoch_counter": int(lo.epoch_counter),
        "epoch_duration_s": int(lo.epoch_duration),
    }


def format_not_idle_message(operation: str, status: dict[str, Any]) -> str:
    """Build a manager-facing message for a non-idle write attempt."""
    phase = status.get("phase")
    name = status.get("phase_name") or phase_name(int(phase or 0))
    epoch = status.get("epoch_counter", "?")
    duration = status.get("epoch_duration_s", "?")
    return (
        f"Cannot {operation}: protocol is in {name} (phase {phase}), epoch {epoch}.\n"
        "Writes are only allowed while Idle. Retry after the current epoch finishes "
        f"(~epoch duration {duration}s) or run: orion protocol-status"
    )


def wait_until_idle(
    timeout_s: float,
    poll_s: float = 5.0,
    *,
    operation: str = "operation",
    on_tick: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Poll until the protocol is Idle, or raise ``SystemNotIdleError`` on timeout.

    Args:
        timeout_s: Maximum seconds to wait.
        poll_s: Seconds between polls (minimum 0.1s).
        operation: Verb phrase used in a timeout error (e.g. ``"submit order intent"``).
        on_tick: Optional callback invoked with each ``protocol_status()`` snapshot.

    Returns:
        The status dict observed when Idle.

    Raises:
        SystemNotIdleError: If still not idle when ``timeout_s`` elapses.
        ValueError: If ``timeout_s`` is not positive.
    """
    from .contracts import SystemNotIdleError

    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    poll_s = max(0.1, float(poll_s))
    deadline = time.monotonic() + float(timeout_s)
    last_status: dict[str, Any] = {
        "is_system_idle": False,
        "phase": -1,
        "phase_name": "Unknown",
        "epoch_counter": 0,
        "epoch_duration_s": 0,
    }
    while True:
        last_status = protocol_status()
        if on_tick is not None:
            on_tick(last_status)
        if last_status["is_system_idle"]:
            return last_status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_s, remaining))

    message = format_not_idle_message(operation, last_status)
    message = f"Timed out after {timeout_s:g}s waiting for Idle.\n{message}"
    raise SystemNotIdleError(
        message,
        operation=operation,
        status=last_status,
        hint="Increase --wait-timeout or retry when orion protocol-status shows Idle.",
    )
