"""Tests for protocol idle / phase UX helpers."""

from unittest.mock import patch

import pytest
from orion_finance_sdk_py.contracts import SystemNotIdleError
from orion_finance_sdk_py.protocol import (
    PHASE_NAMES,
    format_not_idle_message,
    phase_name,
    protocol_status,
    wait_until_idle,
)


def test_phase_name_known_and_unknown():
    assert phase_name(0) == "Idle"
    assert phase_name(2) == "SellingLeg"
    assert PHASE_NAMES[4] == "ProcessVaultOperations"
    assert phase_name(99) == "Unknown(99)"


def test_format_not_idle_message_includes_phase_and_epoch():
    msg = format_not_idle_message(
        "submit order intent",
        {
            "phase": 2,
            "phase_name": "SellingLeg",
            "epoch_counter": 17,
            "epoch_duration_s": 86400,
        },
    )
    assert "Cannot submit order intent" in msg
    assert "SellingLeg" in msg
    assert "phase 2" in msg
    assert "epoch 17" in msg
    assert "86400" in msg
    assert "orion protocol-status" in msg


@patch("orion_finance_sdk_py.contracts.LiquidityOrchestrator")
@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_protocol_status_snapshot(MockConfig, MockLO):
    MockConfig.return_value.is_system_idle.return_value = False
    lo = MockLO.return_value
    lo.current_phase = 1
    lo.epoch_counter = 42
    lo.epoch_duration = 3600

    status = protocol_status()
    assert status == {
        "is_system_idle": False,
        "phase": 1,
        "phase_name": "StateCommitment",
        "epoch_counter": 42,
        "epoch_duration_s": 3600,
    }


@patch("orion_finance_sdk_py.protocol.protocol_status")
def test_wait_until_idle_succeeds_after_polls(mock_status):
    mock_status.side_effect = [
        {
            "is_system_idle": False,
            "phase": 2,
            "phase_name": "SellingLeg",
            "epoch_counter": 1,
            "epoch_duration_s": 10,
        },
        {
            "is_system_idle": True,
            "phase": 0,
            "phase_name": "Idle",
            "epoch_counter": 2,
            "epoch_duration_s": 10,
        },
    ]
    ticks: list[dict] = []
    with patch("orion_finance_sdk_py.protocol.time.sleep"):
        status = wait_until_idle(
            30, poll_s=0.1, operation="submit order intent", on_tick=ticks.append
        )
    assert status["is_system_idle"] is True
    assert len(ticks) == 2


@patch("orion_finance_sdk_py.protocol.protocol_status")
def test_wait_until_idle_timeout_raises(mock_status):
    mock_status.return_value = {
        "is_system_idle": False,
        "phase": 3,
        "phase_name": "BuyingLeg",
        "epoch_counter": 9,
        "epoch_duration_s": 100,
    }
    with patch("orion_finance_sdk_py.protocol.time.sleep"):
        with pytest.raises(SystemNotIdleError, match="Timed out") as exc_info:
            wait_until_idle(0.2, poll_s=0.1, operation="submit order intent")
    err = exc_info.value
    assert err.operation == "submit order intent"
    assert err.status["phase_name"] == "BuyingLeg"
    assert err.hint is not None


def test_wait_until_idle_rejects_nonpositive_timeout():
    with pytest.raises(ValueError, match="timeout_s"):
        wait_until_idle(0)


@patch("orion_finance_sdk_py.protocol.protocol_status")
@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_require_system_idle_enriches_error(MockConfig, mock_status):
    from orion_finance_sdk_py.contracts import require_system_idle

    MockConfig.return_value.is_system_idle.return_value = False
    mock_status.return_value = {
        "is_system_idle": False,
        "phase": 1,
        "phase_name": "StateCommitment",
        "epoch_counter": 5,
        "epoch_duration_s": 60,
    }
    with pytest.raises(SystemNotIdleError, match="StateCommitment") as exc_info:
        require_system_idle("submit order intent")
    err = exc_info.value
    assert err.operation == "submit order intent"
    assert err.status["epoch_counter"] == 5
