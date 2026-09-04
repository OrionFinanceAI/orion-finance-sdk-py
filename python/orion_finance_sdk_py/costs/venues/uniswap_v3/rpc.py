"""Archival mainnet RPC helpers for Uniswap v3 snapshots."""

from __future__ import annotations

from urllib.parse import urlparse

from eth_abi import decode, encode
from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.types import HexStr, TxParams

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MULTICALL3_ADDRESS,
)
from orion_finance_sdk_py.utils import checksum_address

POOL_ABI_FUNCTIONS = {
    "slot0": "0x3850c7bd",
    "liquidity": "0x1a686502",
    "tickSpacing": "0xd0c93a7c",
    "fee": "0xddca3f43",
    "token0": "0x0dfe1681",
    "token1": "0xd21220a7",
    "tickBitmap": "0x5339c296",
    "ticks": "0xf30dba93",
}

TICK_INFO_TYPES = [
    "uint128",
    "int128",
    "uint256",
    "uint256",
    "int56",
    "uint160",
    "uint32",
    "bool",
]
FACTORY_GET_POOL = "0x1698ee82"


def encode_call(selector: str, args: bytes = b"") -> bytes:
    """Encode a 4-byte selector plus ABI-encoded arguments."""
    hex_sel = selector[2:] if selector.startswith("0x") else selector
    return bytes.fromhex(hex_sel) + args


def connect_mainnet(rpc_url: str) -> Web3:
    """Connect to Ethereum mainnet and reject other chain IDs."""
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 120}))
    if not w3.is_connected():
        raise RuntimeError(
            f"Failed to connect to mainnet RPC host: {urlparse(rpc_url).hostname}"
        )
    chain_id = int(w3.eth.chain_id)
    if chain_id != 1:
        raise RuntimeError(f"Expected mainnet chain_id=1, got {chain_id}")
    return w3


def _eth_call(w3: Web3, to: str, data: str, block_number: int) -> bytes:
    tx: TxParams = {
        "to": checksum_address(to),
        "data": HexStr(data),
    }
    try:
        result = w3.eth.call(tx, block_number)
        return bytes(result)
    except ContractLogicError as exc:
        raise RuntimeError(
            f"eth_call reverted at block {block_number} to={to}: {exc}"
        ) from exc


def call_contract(
    w3: Web3, address: str, selector: str, encoded_args: bytes, block_number: int
) -> bytes:
    """Call a contract function at ``block_number`` and return raw bytes."""
    data = selector + encoded_args.hex()
    return _eth_call(w3, address, data, block_number)


def pool_slot0(w3: Web3, pool: str, block_number: int) -> tuple[int, int]:
    """Return ``(sqrtPriceX96, tick)`` from pool ``slot0``."""
    raw = call_contract(w3, pool, POOL_ABI_FUNCTIONS["slot0"], b"", block_number)
    sqrt_price_x96, tick, *_rest = decode(
        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"], raw
    )
    return int(sqrt_price_x96), int(tick)


def pool_liquidity(w3: Web3, pool: str, block_number: int) -> int:
    """Return the pool's in-range liquidity."""
    raw = call_contract(w3, pool, POOL_ABI_FUNCTIONS["liquidity"], b"", block_number)
    return int(decode(["uint128"], raw)[0])


def pool_tick_spacing(w3: Web3, pool: str, block_number: int) -> int:
    """Return the pool tick spacing."""
    raw = call_contract(w3, pool, POOL_ABI_FUNCTIONS["tickSpacing"], b"", block_number)
    return int(decode(["int24"], raw)[0])


def pool_fee(w3: Web3, pool: str, block_number: int) -> int:
    """Return the pool fee in hundredths of a bip."""
    raw = call_contract(w3, pool, POOL_ABI_FUNCTIONS["fee"], b"", block_number)
    return int(decode(["uint24"], raw)[0])


def pool_token(w3: Web3, pool: str, fn: str, block_number: int) -> str:
    """Return ``token0`` or ``token1`` for ``fn``."""
    raw = call_contract(w3, pool, POOL_ABI_FUNCTIONS[fn], b"", block_number)
    return checksum_address(decode(["address"], raw)[0])


def factory_get_pool(
    w3: Web3, factory: str, token_a: str, token_b: str, fee: int, block_number: int
) -> str:
    """Return the Uniswap v3 pool address for the given tokens and fee."""
    encoded = encode(
        ["address", "address", "uint24"],
        [
            checksum_address(token_a),
            checksum_address(token_b),
            fee,
        ],
    )
    raw = call_contract(w3, factory, FACTORY_GET_POOL, encoded, block_number)
    return checksum_address(decode(["address"], raw)[0])


def multicall_aggregate3(
    w3: Web3,
    calls: list[tuple[str, bytes]],
    block_number: int,
    batch_size: int = 500,
) -> list[bytes | None]:
    """Batch eth_call via Multicall3. Returns None for failed sub-calls."""
    if not calls:
        return []

    aggregate_selector = Web3.keccak(text="aggregate3((address,bool,bytes)[])")[:4]
    out: list[bytes | None] = []

    for i in range(0, len(calls), batch_size):
        chunk = calls[i : i + batch_size]
        tuples = [
            (checksum_address(target), True, data) for target, data in chunk
        ]
        encoded = encode(["(address,bool,bytes)[]"], [tuples])
        raw = _eth_call(
            w3,
            MULTICALL3_ADDRESS,
            aggregate_selector.hex() + encoded.hex(),
            block_number,
        )
        results = decode(["(bool,bytes)[]"], raw)[0]
        for success, ret in results:
            out.append(bytes(ret) if success and ret else None)

    return out
