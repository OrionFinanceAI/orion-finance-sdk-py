"""Tests for public RPC defaults and probing."""

from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.rpc import (
    DEFAULT_PUBLIC_RPC_URLS,
    clear_default_rpc_cache,
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
