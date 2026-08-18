"""Mocked unit tests for Uniswap v3 archival RPC helpers."""

from unittest.mock import MagicMock, patch

import pytest
from eth_abi import encode
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MULTICALL3_ADDRESS,
    USDC_ADDRESS,
    WETH_ADDRESS,
    WETH_USDC_POOL,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.rpc import (
    connect_mainnet,
    encode_call,
    factory_get_pool,
    multicall_aggregate3,
    pool_fee,
    pool_liquidity,
    pool_slot0,
    pool_tick_spacing,
    pool_token,
)
from web3.exceptions import ContractLogicError

FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"


def _w3_returning(payload: bytes) -> MagicMock:
    w3 = MagicMock()
    w3.eth.call.return_value = payload
    return w3


def test_encode_call_with_and_without_0x_prefix():
    assert encode_call("0x3850c7bd") == bytes.fromhex("3850c7bd")
    assert encode_call("3850c7bd") == bytes.fromhex("3850c7bd")
    assert (
        encode_call("0x3850c7bd", b"\x01\x02")
        == bytes.fromhex("3850c7bd") + b"\x01\x02"
    )


def test_connect_mainnet_accepts_chain_id_1():
    with patch("orion_finance_sdk_py.costs.venues.uniswap_v3.rpc.Web3") as mock_web3:
        instance = MagicMock()
        instance.is_connected.return_value = True
        instance.eth.chain_id = 1
        mock_web3.return_value = instance
        assert connect_mainnet("https://example.invalid") is instance


def test_connect_mainnet_rejects_disconnected():
    with patch("orion_finance_sdk_py.costs.venues.uniswap_v3.rpc.Web3") as mock_web3:
        instance = MagicMock()
        instance.is_connected.return_value = False
        mock_web3.return_value = instance
        with pytest.raises(RuntimeError, match="Failed to connect"):
            connect_mainnet("https://example.invalid")


def test_connect_mainnet_rejects_wrong_chain():
    with patch("orion_finance_sdk_py.costs.venues.uniswap_v3.rpc.Web3") as mock_web3:
        instance = MagicMock()
        instance.is_connected.return_value = True
        instance.eth.chain_id = 11155111
        mock_web3.return_value = instance
        with pytest.raises(RuntimeError, match="chain_id=1"):
            connect_mainnet("https://example.invalid")


def test_pool_slot0_decodes_sqrt_price_and_tick():
    raw = encode(
        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
        [123456, -10, 0, 0, 0, 0, True],
    )
    sqrt_price, tick = pool_slot0(_w3_returning(raw), WETH_USDC_POOL, 1)
    assert sqrt_price == 123456
    assert tick == -10


def test_pool_liquidity_tick_spacing_fee_and_token():
    w3 = _w3_returning(encode(["uint128"], [99]))
    assert pool_liquidity(w3, WETH_USDC_POOL, 1) == 99

    w3 = _w3_returning(encode(["int24"], [10]))
    assert pool_tick_spacing(w3, WETH_USDC_POOL, 1) == 10

    w3 = _w3_returning(encode(["uint24"], [500]))
    assert pool_fee(w3, WETH_USDC_POOL, 1) == 500

    w3 = _w3_returning(encode(["address"], [USDC_ADDRESS]))
    assert pool_token(w3, WETH_USDC_POOL, "token0", 1) == USDC_ADDRESS


def test_eth_call_reverts_become_runtime_error():
    w3 = MagicMock()
    w3.eth.call.side_effect = ContractLogicError("revert")
    with pytest.raises(RuntimeError, match="eth_call reverted"):
        pool_liquidity(w3, WETH_USDC_POOL, 42)


def test_factory_get_pool_decodes_address():
    w3 = _w3_returning(encode(["address"], [WETH_USDC_POOL]))
    pool = factory_get_pool(w3, FACTORY, WETH_ADDRESS, USDC_ADDRESS, 500, 1)
    assert pool == WETH_USDC_POOL


def test_multicall_aggregate3_empty_calls():
    assert multicall_aggregate3(MagicMock(), [], 1) == []


def test_multicall_aggregate3_success_and_failed_subcalls():
    payload = encode(["uint256"], [7])
    raw = encode(["(bool,bytes)[]"], [[(True, payload), (False, b""), (True, b"")]])
    w3 = _w3_returning(raw)
    dummy = encode_call("0x5339c296")
    out = multicall_aggregate3(
        w3,
        [(WETH_USDC_POOL, dummy), (WETH_USDC_POOL, dummy), (WETH_USDC_POOL, dummy)],
        1,
    )
    assert out[0] == payload
    assert out[1] is None
    assert out[2] is None
    w3.eth.call.assert_called_once()
    tx = w3.eth.call.call_args.args[0]
    assert tx["to"] == MULTICALL3_ADDRESS


def test_multicall_aggregate3_batches():
    a = encode(["uint256"], [1])
    b = encode(["uint256"], [2])
    w3 = MagicMock()
    w3.eth.call.side_effect = [
        encode(["(bool,bytes)[]"], [[(True, a)]]),
        encode(["(bool,bytes)[]"], [[(True, b)]]),
    ]
    dummy = encode_call("0x5339c296")
    out = multicall_aggregate3(
        w3,
        [(WETH_USDC_POOL, dummy), (WETH_USDC_POOL, dummy)],
        1,
        batch_size=1,
    )
    assert out == [a, b]
    assert w3.eth.call.call_count == 2
