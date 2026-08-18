"""Fetch Uniswap v3 pool liquidity snapshots at a pinned block."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

from eth_abi import decode, encode
from web3 import Web3

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MAX_TICK,
    MIN_TICK,
    USDC_ADDRESS,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.rpc import (
    POOL_ABI_FUNCTIONS,
    TICK_INFO_TYPES,
    encode_call,
    multicall_aggregate3,
    pool_fee,
    pool_liquidity,
    pool_slot0,
    pool_tick_spacing,
    pool_token,
)
from orion_finance_sdk_py.erc20 import decimals as erc20_decimals
from orion_finance_sdk_py.erc20 import symbol as erc20_symbol


@dataclass
class PoolMeta:
    """Uniswap v3 pool metadata needed to interpret a snapshot."""

    address: str
    token0: str = ""
    token1: str = ""
    fee: int = 0
    decimals0: int = 18
    decimals1: int = 18
    tick_spacing: int = 0
    stable_token: str | None = None
    symbol0: str = ""
    symbol1: str = ""


@dataclass
class PoolState:
    """Pinned-block Uniswap v3 pool snapshot for swap simulation."""

    meta: PoolMeta
    block_number: int
    sqrt_price_x96: int
    tick: int
    liquidity: int
    tick_liquidity_net: dict[int, int] = field(default_factory=dict)
    initialized_ticks: list[int] = field(default_factory=list)

    def to_json(self) -> dict:
        """Serialize this snapshot to a JSON-compatible dict."""
        return {
            "meta": asdict(self.meta),
            "block_number": self.block_number,
            "sqrt_price_x96": str(self.sqrt_price_x96),
            "tick": self.tick,
            "liquidity": str(self.liquidity),
            "tick_liquidity_net": {
                str(k): str(v) for k, v in self.tick_liquidity_net.items()
            },
            "initialized_ticks": self.initialized_ticks,
        }

    @classmethod
    def from_json(cls, data: dict) -> PoolState:
        """Build a snapshot from ``to_json`` output."""
        allowed = {f.name for f in fields(PoolMeta)}
        meta = PoolMeta(**{k: v for k, v in data["meta"].items() if k in allowed})
        return cls(
            meta=meta,
            block_number=int(data["block_number"]),
            sqrt_price_x96=int(data["sqrt_price_x96"]),
            tick=int(data["tick"]),
            liquidity=int(data["liquidity"]),
            tick_liquidity_net={
                int(k): int(v) for k, v in data["tick_liquidity_net"].items()
            },
            initialized_ticks=[int(t) for t in data["initialized_ticks"]],
        )


def _compress_tick(tick: int, tick_spacing: int) -> int:
    c = tick // tick_spacing
    if tick < 0 and tick % tick_spacing != 0:
        c -= 1
    return c


def _decompress_tick(compressed: int, tick_spacing: int) -> int:
    return compressed * tick_spacing


def scan_initialized_ticks(
    w3: Web3, pool: str, tick_spacing: int, block_number: int
) -> list[int]:
    """Return initialized ticks in the pool at ``block_number``."""
    min_word = _compress_tick(MIN_TICK, tick_spacing) >> 8
    max_word = _compress_tick(MAX_TICK, tick_spacing) >> 8

    words = list(range(min_word, max_word + 1))
    bitmap_calls = [
        (
            pool,
            encode_call(POOL_ABI_FUNCTIONS["tickBitmap"], encode(["int16"], [w])),
        )
        for w in words
    ]

    bitmap_results = multicall_aggregate3(w3, bitmap_calls, block_number)
    initialized: list[int] = []
    for word_pos, raw in zip(words, bitmap_results, strict=True):
        if raw is None:
            continue
        bitmap = int(decode(["uint256"], raw)[0])
        if bitmap == 0:
            continue
        for bit in range(256):
            if (bitmap >> bit) & 1:
                compressed = (word_pos << 8) + bit
                initialized.append(_decompress_tick(compressed, tick_spacing))

    return sorted(initialized)


def fetch_tick_liquidity_net(
    w3: Web3,
    pool: str,
    ticks: list[int],
    block_number: int,
    batch_size: int = 200,
) -> dict[int, int]:
    """Return ``tick -> liquidityNet`` for ``ticks`` at ``block_number``."""
    tick_net: dict[int, int] = {}
    for i in range(0, len(ticks), batch_size):
        batch = ticks[i : i + batch_size]
        calls = [
            (
                pool,
                encode_call(POOL_ABI_FUNCTIONS["ticks"], encode(["int24"], [t])),
            )
            for t in batch
        ]
        results = multicall_aggregate3(w3, calls, block_number)
        for tick, raw in zip(batch, results, strict=True):
            if raw is None or len(raw) < 64:
                continue
            _gross, net, *_ = decode(TICK_INFO_TYPES, raw)
            if int(net) != 0:
                tick_net[tick] = int(net)
    return tick_net


def _token_symbol(w3: Web3, token: str, block_number: int) -> str:
    try:
        return erc20_symbol(w3, token, block=block_number)
    except Exception:
        return token[-4:]


def _resolve_usdc_side(meta: PoolMeta) -> None:
    usdc = USDC_ADDRESS.lower()
    if meta.token0.lower() == usdc:
        meta.stable_token = meta.token0
    elif meta.token1.lower() == usdc:
        meta.stable_token = meta.token1
    else:
        meta.stable_token = None


def enrich_pool_meta(w3: Web3, meta: PoolMeta, block_number: int) -> PoolMeta:
    """Fill token, fee, decimals, and symbols on ``meta`` from chain state."""
    meta.token0 = pool_token(w3, meta.address, "token0", block_number)
    meta.token1 = pool_token(w3, meta.address, "token1", block_number)
    meta.fee = pool_fee(w3, meta.address, block_number)
    meta.tick_spacing = pool_tick_spacing(w3, meta.address, block_number)
    meta.decimals0 = erc20_decimals(w3, meta.token0, block=block_number)
    meta.decimals1 = erc20_decimals(w3, meta.token1, block=block_number)
    meta.symbol0 = _token_symbol(w3, meta.token0, block_number)
    meta.symbol1 = _token_symbol(w3, meta.token1, block_number)
    _resolve_usdc_side(meta)
    return meta


def fetch_pool_state(w3: Web3, meta: PoolMeta, block_number: int) -> PoolState:
    """Fetch slot0, liquidity, and tick bitmap state at ``block_number``."""
    sqrt_price_x96, tick = pool_slot0(w3, meta.address, block_number)
    liquidity = pool_liquidity(w3, meta.address, block_number)
    initialized = scan_initialized_ticks(
        w3, meta.address, meta.tick_spacing, block_number
    )
    tick_net = fetch_tick_liquidity_net(w3, meta.address, initialized, block_number)

    return PoolState(
        meta=meta,
        block_number=block_number,
        sqrt_price_x96=sqrt_price_x96,
        tick=tick,
        liquidity=liquidity,
        tick_liquidity_net=tick_net,
        initialized_ticks=initialized,
    )
