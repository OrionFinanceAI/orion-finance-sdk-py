"""Tests for public RPC defaults and probing."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.rpc import (
    DEFAULT_PUBLIC_MAINNET_RPC_URLS,
    DEFAULT_PUBLIC_RPC_URLS,
    block_at_timestamp,
    call_with_rpc_retry,
    clear_default_rpc_cache,
    pick_default_mainnet_rpc,
    pick_default_rpc,
    rpc_works,
)


def setup_function():
    clear_default_rpc_cache()


def teardown_function():
    clear_default_rpc_cache()


def test_default_public_rpc_urls_match_install_order():
    assert DEFAULT_PUBLIC_RPC_URLS == (
        "https://1rpc.io/sepolia",
        "https://0xrpc.io/sep",
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://evm.stupidtech.net/v1/11155111",
    )


def test_rpc_works_true_when_connected():
    with patch("web3.Web3") as MockWeb3:
        instance = MagicMock()
        instance.is_connected.return_value = True
        MockWeb3.return_value = instance
        assert rpc_works("https://example.invalid") is True


def test_rpc_works_false_on_error():
    with patch("web3.Web3", side_effect=RuntimeError("boom")):
        assert rpc_works("https://example.invalid") is False


def test_pick_default_rpc_tries_in_order_and_caches():
    calls: list[str] = []

    def _works(url, timeout=5.0):
        calls.append(url)
        return url == DEFAULT_PUBLIC_RPC_URLS[1]

    with patch("orion_finance_sdk_py.rpc.rpc_works", side_effect=_works):
        assert pick_default_rpc() == DEFAULT_PUBLIC_RPC_URLS[1]
        # Second call uses cache - no more probes
        assert pick_default_rpc() == DEFAULT_PUBLIC_RPC_URLS[1]

    assert calls == [DEFAULT_PUBLIC_RPC_URLS[0], DEFAULT_PUBLIC_RPC_URLS[1]]


def test_pick_default_rpc_returns_none_when_all_fail():
    with patch("orion_finance_sdk_py.rpc.rpc_works", return_value=False):
        assert pick_default_rpc() is None


def test_default_public_mainnet_rpc_urls_order():
    assert DEFAULT_PUBLIC_MAINNET_RPC_URLS == (
        "https://ethereum-rpc.publicnode.com",
        "https://eth-mainnet.g.alchemy.com/public",
        "https://public.1rpc.io/eth",
        "https://eth.drpc.org/",
    )


def test_pick_default_mainnet_rpc_tries_in_order_and_caches():
    calls: list[str] = []

    def _works(url, timeout=5.0):
        calls.append(url)
        return url == DEFAULT_PUBLIC_MAINNET_RPC_URLS[1]

    with patch("orion_finance_sdk_py.rpc.rpc_works", side_effect=_works):
        assert pick_default_mainnet_rpc() == DEFAULT_PUBLIC_MAINNET_RPC_URLS[1]
        assert pick_default_mainnet_rpc() == DEFAULT_PUBLIC_MAINNET_RPC_URLS[1]

    assert calls == [
        DEFAULT_PUBLIC_MAINNET_RPC_URLS[0],
        DEFAULT_PUBLIC_MAINNET_RPC_URLS[1],
    ]


def test_pick_default_mainnet_rpc_returns_none_when_all_fail():
    with patch("orion_finance_sdk_py.rpc.rpc_works", return_value=False):
        assert pick_default_mainnet_rpc() is None


def test_clear_default_rpc_cache_resets_mainnet_cache():
    with patch(
        "orion_finance_sdk_py.rpc.rpc_works",
        return_value=True,
    ):
        assert pick_default_mainnet_rpc() == DEFAULT_PUBLIC_MAINNET_RPC_URLS[0]
    clear_default_rpc_cache()
    calls: list[str] = []

    def _works(url, timeout=5.0):
        calls.append(url)
        return True

    with patch("orion_finance_sdk_py.rpc.rpc_works", side_effect=_works):
        assert pick_default_mainnet_rpc() == DEFAULT_PUBLIC_MAINNET_RPC_URLS[0]
    assert calls == [DEFAULT_PUBLIC_MAINNET_RPC_URLS[0]]


def test_call_with_rpc_retry_succeeds_after_connection_error():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("reset by peer")
        return "ok"

    with patch("orion_finance_sdk_py.rpc.time.sleep") as sleep:
        assert call_with_rpc_retry(flaky, retries=3, backoff_factor=0.01) == "ok"
        sleep.assert_called_once()
    assert calls["n"] == 2


def test_call_with_rpc_retry_exhausts_and_reraises():
    with patch("orion_finance_sdk_py.rpc.time.sleep"):
        with pytest.raises(ConnectionError, match="still down"):
            call_with_rpc_retry(
                lambda: (_ for _ in ()).throw(ConnectionError("still down")),
                retries=3,
                backoff_factor=0.01,
            )


def test_call_with_rpc_retry_does_not_retry_value_error():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        call_with_rpc_retry(boom, retries=5, backoff_factor=0.01)
    assert calls["n"] == 1


def test_block_at_timestamp_respects_bounds():
    w3 = MagicMock()
    timestamps = {10: 1000, 11: 1100, 12: 1200, 13: 1300, 14: 1400}
    w3.eth.get_block.side_effect = lambda n: {"timestamp": timestamps[int(n)]}

    assert block_at_timestamp(w3, 1250, lo=10, hi=14) == 12
    # Does not fetch genesis or tip outside the window
    fetched = {int(c.args[0]) for c in w3.eth.get_block.call_args_list}
    assert 0 not in fetched
    assert fetched <= set(timestamps)


def test_block_at_timestamp_rejects_negative():
    w3 = MagicMock()
    with pytest.raises(ValueError, match="non-negative"):
        block_at_timestamp(w3, -1)
