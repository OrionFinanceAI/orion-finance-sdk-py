"""Minimal ERC-20 helpers for approvals and transfers."""

from __future__ import annotations

import os
from typing import Any

from web3 import Web3

from .console_ui import progress_step
from .contracts import TransactionResult
from .utils import validate_var

IERC20_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "allowance",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "transfer",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "transferFrom",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "decimals",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "type": "function",
        "name": "symbol",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
]


def get_erc20(w3: Web3, token_address: str):
    """Return a web3 contract instance for an ERC-20 token."""
    return w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=IERC20_ABI,
    )


def allowance(w3: Web3, token_address: str, owner: str, spender: str) -> int:
    """Read ERC-20 allowance."""
    token = get_erc20(w3, token_address)
    return token.functions.allowance(
        Web3.to_checksum_address(owner),
        Web3.to_checksum_address(spender),
    ).call()


def balance_of(w3: Web3, token_address: str, account: str) -> int:
    """Read ERC-20 balance."""
    token = get_erc20(w3, token_address)
    return token.functions.balanceOf(Web3.to_checksum_address(account)).call()


def decimals(w3: Web3, token_address: str, block: int | None = None) -> int:
    """Read ERC-20 decimals."""
    token = get_erc20(w3, token_address)
    call_kw = {} if block is None else {"block_identifier": block}
    return int(token.functions.decimals().call(**call_kw))


def symbol(w3: Web3, token_address: str, block: int | None = None) -> str:
    """Read ERC-20 symbol."""
    token = get_erc20(w3, token_address)
    call_kw = {} if block is None else {"block_identifier": block}
    value = token.functions.symbol().call(**call_kw)
    if isinstance(value, bytes):
        return value.rstrip(b"\x00").decode("utf-8")
    return str(value)


def _send_token_tx(w3: Web3, fn, key: str, action: str) -> TransactionResult:
    """Sign and send an ERC-20 state-changing call."""
    account = w3.eth.account.from_key(key)
    tx = fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = account.sign_transaction(tx)
    progress_step(f"Broadcasting ERC-20 {action}")
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    progress_step("Waiting for confirmation")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] != 1:
        raise Exception(f"ERC-20 {action} failed with status: {receipt['status']}")
    return TransactionResult(tx_hash=tx_hash.hex(), receipt=receipt, decoded_logs=None)


def approve(
    w3: Web3,
    token_address: str,
    spender: str,
    amount: int,
    *,
    key_env: str = "LP_PRIVATE_KEY",
    private_key: str | None = None,
) -> TransactionResult:
    """Approve ``spender`` to transfer ``amount`` of ``token_address``."""
    key = private_key or validate_var(
        os.getenv(key_env),
        error_message=f"{key_env} environment variable is missing or invalid.",
    )
    token = get_erc20(w3, token_address)
    fn = token.functions.approve(Web3.to_checksum_address(spender), amount)
    return _send_token_tx(w3, fn, key, "approve")


def transfer(
    w3: Web3,
    token_address: str,
    to: str,
    amount: int,
    *,
    key_env: str = "LP_PRIVATE_KEY",
    private_key: str | None = None,
) -> TransactionResult:
    """Transfer ERC-20 tokens."""
    key = private_key or validate_var(
        os.getenv(key_env),
        error_message=f"{key_env} environment variable is missing or invalid.",
    )
    token = get_erc20(w3, token_address)
    fn = token.functions.transfer(Web3.to_checksum_address(to), amount)
    return _send_token_tx(w3, fn, key, "transfer")
