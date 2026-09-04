"""Tests for LP queue event helpers."""

from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.events import get_lp_events, parse_lp_events_from_receipt

VAULT = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"

_MIN_EVENT_ABI = [
    {
        "type": "event",
        "name": "DepositRequest",
        "inputs": [
            {"name": "sender", "type": "address", "indexed": True},
            {"name": "assets", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
    {
        "type": "event",
        "name": "DepositRequestCancelled",
        "inputs": [
            {"name": "user", "type": "address", "indexed": True},
            {"name": "amount", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
    {
        "type": "event",
        "name": "RedeemRequest",
        "inputs": [
            {"name": "sender", "type": "address", "indexed": True},
            {"name": "shares", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
    {
        "type": "event",
        "name": "RedeemRequestCancelled",
        "inputs": [
            {"name": "user", "type": "address", "indexed": True},
            {"name": "shares", "type": "uint256", "indexed": False},
        ],
        "anonymous": False,
    },
]


@patch("orion_finance_sdk_py.events.load_contract_abi", return_value=_MIN_EVENT_ABI)
def test_parse_lp_events_decodes_matching_log(mock_abi):
    w3 = MagicMock()
    contract = MagicMock()
    w3.eth.contract.return_value = contract

    event_instance = MagicMock()
    event_instance.process_log.return_value = {
        "event": "DepositRequest",
        "args": {"sender": VAULT, "assets": 100},
        "address": VAULT,
        "logIndex": 1,
    }
    contract.events = {"DepositRequest": MagicMock(return_value=event_instance)}
    for name in (
        "DepositRequestCancelled",
        "RedeemRequest",
        "RedeemRequestCancelled",
    ):
        bad = MagicMock()
        bad.process_log.side_effect = Exception("no match")
        contract.events[name] = MagicMock(return_value=bad)

    # First event name tried wins when process_log succeeds — put DepositRequest first
    # by iterating ABI order; ensure DepositRequest process_log works on first try
    # Reset: make DepositRequest succeed, others unused after break
    def events_get(name):
        inst = MagicMock()
        if name == "DepositRequest":
            inst.process_log.return_value = {
                "event": "DepositRequest",
                "args": {"sender": "0xS", "assets": 100},
                "address": VAULT,
                "logIndex": 1,
            }
        else:
            inst.process_log.side_effect = Exception("mismatch")
        return MagicMock(return_value=inst)()

    # Simpler: use a dict of callables that return event instances
    event_objs = {}
    for name in (
        "DepositRequest",
        "DepositRequestCancelled",
        "RedeemRequest",
        "RedeemRequestCancelled",
    ):
        inst = MagicMock()
        if name == "DepositRequest":
            inst.process_log.return_value = {
                "event": "DepositRequest",
                "args": {"sender": "0xS", "assets": 100},
                "address": VAULT,
                "logIndex": 1,
            }
        else:
            inst.process_log.side_effect = Exception("mismatch")
        event_objs[name] = MagicMock(return_value=inst)

    contract.events = event_objs

    receipt = {"logs": [{"address": VAULT, "topics": []}]}
    decoded = parse_lp_events_from_receipt(w3, receipt)
    assert len(decoded) == 1
    assert decoded[0]["event"] == "DepositRequest"
    assert decoded[0]["args"]["assets"] == 100


@patch("orion_finance_sdk_py.events.load_contract_abi", return_value=_MIN_EVENT_ABI)
def test_parse_lp_events_filters_by_vault_address(mock_abi):
    w3 = MagicMock()
    contract = MagicMock()
    w3.eth.contract.return_value = contract
    event_objs = {}
    for name in (
        "DepositRequest",
        "DepositRequestCancelled",
        "RedeemRequest",
        "RedeemRequestCancelled",
    ):
        inst = MagicMock()
        inst.process_log.side_effect = Exception("should not run")
        event_objs[name] = MagicMock(return_value=inst)
    contract.events = event_objs

    receipt = {"logs": [{"address": OTHER, "topics": []}]}
    assert parse_lp_events_from_receipt(w3, receipt, vault_address=VAULT) == []


@patch("orion_finance_sdk_py.events.load_contract_abi", return_value=_MIN_EVENT_ABI)
def test_parse_lp_events_skips_non_matching_log(mock_abi):
    w3 = MagicMock()
    contract = MagicMock()
    w3.eth.contract.return_value = contract
    event_objs = {}
    for name in (
        "DepositRequest",
        "DepositRequestCancelled",
        "RedeemRequest",
        "RedeemRequestCancelled",
    ):
        inst = MagicMock()
        inst.process_log.side_effect = Exception("mismatch")
        event_objs[name] = MagicMock(return_value=inst)
    contract.events = event_objs

    receipt = {"logs": [{"address": VAULT, "topics": []}]}
    assert parse_lp_events_from_receipt(w3, receipt) == []


@patch("orion_finance_sdk_py.events.load_contract_abi", return_value=_MIN_EVENT_ABI)
def test_get_lp_events_aggregates_and_sorts(mock_abi):
    w3 = MagicMock()
    contract = MagicMock()
    w3.eth.contract.return_value = contract

    tx_hash = MagicMock()
    tx_hash.hex.return_value = "0xdead"

    later = {
        "event": "RedeemRequest",
        "args": {"sender": "0xA", "shares": 2},
        "address": VAULT,
        "blockNumber": 20,
        "transactionHash": tx_hash,
        "logIndex": 0,
    }
    earlier = {
        "event": "DepositRequest",
        "args": {"sender": "0xA", "assets": 1},
        "address": VAULT,
        "blockNumber": 10,
        "transactionHash": tx_hash,
        "logIndex": 0,
    }

    deposit_event = MagicMock()
    deposit_event.get_logs.return_value = [earlier]
    redeem_event = MagicMock()
    redeem_event.get_logs.return_value = [later]
    cancel_dep = MagicMock()
    cancel_dep.get_logs.return_value = []
    cancel_red = MagicMock()
    cancel_red.get_logs.return_value = []

    contract.events.DepositRequest = deposit_event
    contract.events.DepositRequestCancelled = cancel_dep
    contract.events.RedeemRequest = redeem_event
    contract.events.RedeemRequestCancelled = cancel_red

    results = get_lp_events(w3, VAULT)
    assert [r["event"] for r in results] == ["DepositRequest", "RedeemRequest"]
    assert results[0]["transactionHash"] == "0xdead"


@patch("orion_finance_sdk_py.events.load_contract_abi", return_value=_MIN_EVENT_ABI)
def test_get_lp_events_custom_names_and_null_tx_hash(mock_abi):
    w3 = MagicMock()
    contract = MagicMock()
    w3.eth.contract.return_value = contract

    entry = {
        "event": "DepositRequest",
        "args": {"sender": "0xA", "assets": 1},
        "address": VAULT,
        "blockNumber": 1,
        "transactionHash": None,
        "logIndex": 0,
    }
    deposit_event = MagicMock()
    deposit_event.get_logs.return_value = [entry]
    contract.events.DepositRequest = deposit_event

    results = get_lp_events(w3, VAULT, event_names=("DepositRequest",))
    assert len(results) == 1
    assert results[0]["transactionHash"] is None
