"""Tests for ERC-20 helpers."""

import os
from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.erc20 import (
    _send_token_tx,
    allowance,
    approve,
    balance_of,
    decimals,
    get_erc20,
    symbol,
    transfer,
)

TOKEN = "0x1111111111111111111111111111111111111111"
SPENDER = "0x2222222222222222222222222222222222222222"
OWNER = "0x3333333333333333333333333333333333333333"


def _mock_w3_with_success_tx():
    w3 = MagicMock()
    account = MagicMock()
    account.address = OWNER
    signed = MagicMock()
    signed.raw_transaction = b"signed"
    account.sign_transaction.return_value = signed
    w3.eth.account.from_key.return_value = account
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.gas_price = 1
    tx_hash = MagicMock()
    tx_hash.hex.return_value = "0xabc"
    w3.eth.send_raw_transaction.return_value = tx_hash
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
    w3.eth.contract.return_value = MagicMock()
    return w3


def test_get_erc20_builds_contract():
    w3 = MagicMock()
    get_erc20(w3, TOKEN)
    w3.eth.contract.assert_called_once()
    kwargs = w3.eth.contract.call_args.kwargs
    assert "abi" in kwargs


def test_allowance_calls_token():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.allowance.return_value.call.return_value = 42
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert allowance(w3, TOKEN, OWNER, SPENDER) == 42
    token.functions.allowance.assert_called_once()


def test_balance_of_calls_token():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.balanceOf.return_value.call.return_value = 99
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert balance_of(w3, TOKEN, OWNER) == 99


def test_decimals_calls_token():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.decimals.return_value.call.return_value = 6
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert decimals(w3, TOKEN) == 6
    token.functions.decimals.assert_called_once()
    token.functions.decimals.return_value.call.assert_called_once_with()


def test_decimals_passes_block_identifier():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.decimals.return_value.call.return_value = 6
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert decimals(w3, TOKEN, block=12_345_678) == 6
    token.functions.decimals.return_value.call.assert_called_once_with(
        block_identifier=12_345_678
    )


def test_symbol_calls_token():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.symbol.return_value.call.return_value = "USDC"
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert symbol(w3, TOKEN) == "USDC"
    token.functions.symbol.return_value.call.assert_called_once_with()


def test_symbol_passes_block_identifier():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.symbol.return_value.call.return_value = "USDC"
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert symbol(w3, TOKEN, block=99) == "USDC"
    token.functions.symbol.return_value.call.assert_called_once_with(
        block_identifier=99
    )


def test_symbol_decodes_bytes32():
    w3 = MagicMock()
    token = MagicMock()
    token.functions.symbol.return_value.call.return_value = b"USDC" + b"\x00" * 28
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        assert symbol(w3, TOKEN) == "USDC"


def test_approve_with_explicit_private_key():
    w3 = _mock_w3_with_success_tx()
    token = MagicMock()
    fn = MagicMock()
    fn.build_transaction.return_value = {}
    token.functions.approve.return_value = fn
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        res = approve(w3, TOKEN, SPENDER, 100, private_key="0xkey")
    assert res.tx_hash == "0xabc"
    assert res.receipt["status"] == 1
    token.functions.approve.assert_called_once()


def test_approve_reads_env_key():
    w3 = _mock_w3_with_success_tx()
    token = MagicMock()
    fn = MagicMock()
    fn.build_transaction.return_value = {}
    token.functions.approve.return_value = fn
    with patch.dict(os.environ, {"LP_PRIVATE_KEY": "0xenvkey"}):
        with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
            res = approve(w3, TOKEN, SPENDER, 1)
    assert res.tx_hash == "0xabc"
    w3.eth.account.from_key.assert_called_with("0xenvkey")


def test_transfer_success():
    w3 = _mock_w3_with_success_tx()
    token = MagicMock()
    fn = MagicMock()
    fn.build_transaction.return_value = {}
    token.functions.transfer.return_value = fn
    with patch("orion_finance_sdk_py.erc20.get_erc20", return_value=token):
        res = transfer(w3, TOKEN, SPENDER, 7, private_key="0xkey")
    assert res.tx_hash == "0xabc"
    token.functions.transfer.assert_called_once()


def test_send_token_tx_raises_on_failed_receipt():
    w3 = _mock_w3_with_success_tx()
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 0}
    fn = MagicMock()
    fn.build_transaction.return_value = {}
    with pytest.raises(Exception, match="ERC-20 approve failed"):
        _send_token_tx(w3, fn, "0xkey", "approve")
