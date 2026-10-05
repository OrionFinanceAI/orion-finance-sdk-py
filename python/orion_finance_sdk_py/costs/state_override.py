"""ERC-20 storage overrides for eth_call simulation of ``sell``.

Discovers balance / allowance storage for:

* Solidity ``mapping`` layouts (OZ, WBTC, Morpho MetaMorpho, …)
* Vyper ``HashMap`` layouts (Yearn V3 TokenizedStrategy, …)
* Fallback via ``eth_createAccessList`` when layouts are exotic

Validation requires an **exact** ``balanceOf`` / ``allowance`` match to the
overridden amount (avoids false positives when the holder already has a
large on-chain balance).
"""

from __future__ import annotations

from typing import Any, Literal

from eth_utils import keccak
from web3 import Web3
from web3.types import RPCEndpoint

from orion_finance_sdk_py.erc20 import IERC20_ABI
from orion_finance_sdk_py.utils import checksum_address

Layout = Literal["solidity", "vyper"]

# OZ ERC20Upgradeable ERC-7201 namespaced storage location.
_OZ_ERC20_7201 = (
    int.from_bytes(keccak(text="openzeppelin.storage.ERC20"), "big") - 1
) % (2**256)
OZ_ERC20_STORAGE_LOCATION = (
    int.from_bytes(keccak(_OZ_ERC20_7201.to_bytes(32, "big")), "big") & ~0xff
)

# Morpho MetaMorpho uses balances@12 / allowances@13; Yearn Vyper @17/@18.
MAPPING_SLOTS: tuple[int, ...] = tuple(range(0, 20)) + (
    OZ_ERC20_STORAGE_LOCATION,
    OZ_ERC20_STORAGE_LOCATION + 1,
)
BALANCE_MAPPING_SLOTS = MAPPING_SLOTS
ALLOWANCE_MAPPING_SLOT_OFFSET = 1

# Cache: (token, holder, spender) -> (layout, bal_mapping_slot, allow_mapping_slot)
# or raw storage keys when discovered via access list.
_SLOT_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _pad32(value: int | bytes) -> bytes:
    if isinstance(value, int):
        if value < 0 or value >= 2**256:
            raise ValueError("storage values must fit in uint256")
        return value.to_bytes(32, byteorder="big")
    if len(value) > 32:
        raise ValueError("value longer than 32 bytes")
    return value.rjust(32, b"\x00")


def to_storage_hex(value: int) -> str:
    """Encode a uint256 as a 32-byte hex string for ``stateDiff``."""
    return "0x" + _pad32(value).hex()


def mapping_slot(key: str | bytes, base_slot: int) -> bytes:
    """Solidity ``keccak256(abi.encode(key, base_slot))``."""
    if isinstance(key, str):
        key_bytes = bytes.fromhex(checksum_address(key)[2:])
    else:
        key_bytes = key
    if len(key_bytes) != 20:
        raise ValueError("mapping key must be a 20-byte address")
    return keccak(_pad32(key_bytes) + _pad32(base_slot))


def vyper_mapping_slot(key: str | bytes, base_slot: int) -> bytes:
    """Vyper ``HashMap``: ``keccak256(concat(convert(slot, bytes32), key))``."""
    if isinstance(key, str):
        key_bytes = bytes.fromhex(checksum_address(key)[2:])
    else:
        key_bytes = key
    if len(key_bytes) != 20:
        raise ValueError("mapping key must be a 20-byte address")
    return keccak(_pad32(base_slot) + _pad32(key_bytes))


def balance_storage_slot(
    account: str,
    balance_mapping_slot: int = 0,
    *,
    layout: Layout = "solidity",
) -> str:
    """Storage slot for ``balances[account]``."""
    fn = mapping_slot if layout == "solidity" else vyper_mapping_slot
    return "0x" + fn(account, balance_mapping_slot).hex()


def allowance_storage_slot(
    owner: str,
    spender: str,
    allowance_mapping_slot: int = 1,
    *,
    layout: Layout = "solidity",
) -> str:
    """Storage slot for ``allowances[owner][spender]``."""
    owner_c = checksum_address(owner)
    spender_c = checksum_address(spender)
    if layout == "solidity":
        inner = mapping_slot(owner_c, allowance_mapping_slot)
        outer = keccak(_pad32(bytes.fromhex(spender_c[2:])) + inner)
        return "0x" + outer.hex()
    # Vyper nested HashMap: keccak(concat(keccak(concat(slot, owner)), spender))
    inner = vyper_mapping_slot(owner_c, allowance_mapping_slot)
    outer = keccak(inner + _pad32(bytes.fromhex(spender_c[2:])))
    return "0x" + outer.hex()


def build_erc20_state_override(
    token: str,
    *,
    holder: str,
    spender: str,
    amount: int,
    balance_mapping_slot: int = 0,
    allowance_mapping_slot: int | None = None,
    layout: Layout = "solidity",
) -> dict[str, Any]:
    """Build a ``state_override`` giving ``holder`` balance and allowance."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    allow_slot = (
        allowance_mapping_slot
        if allowance_mapping_slot is not None
        else balance_mapping_slot + ALLOWANCE_MAPPING_SLOT_OFFSET
    )
    bal_key = balance_storage_slot(
        holder_c, balance_mapping_slot, layout=layout
    )
    all_key = allowance_storage_slot(
        holder_c, spender_c, allow_slot, layout=layout
    )
    packed = to_storage_hex(amount)
    return {token_c: {"stateDiff": {bal_key: packed, all_key: packed}}}


def build_override_from_keys(
    token: str,
    *,
    balance_key: str,
    allowance_key: str,
    amount: int,
) -> dict[str, Any]:
    """Build a ``state_override`` from raw storage keys."""
    packed = to_storage_hex(amount)
    return {
        checksum_address(token): {
            "stateDiff": {
                balance_key: packed,
                allowance_key: packed,
            }
        }
    }


def _erc20(w3: Web3, token: str):
    return w3.eth.contract(address=checksum_address(token), abi=IERC20_ABI)


def _balance_only_override(
    token: str,
    holder: str,
    amount: int,
    balance_mapping_slot: int,
    *,
    layout: Layout = "solidity",
) -> dict[str, Any]:
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    return {
        token_c: {
            "stateDiff": {
                balance_storage_slot(
                    holder_c, balance_mapping_slot, layout=layout
                ): to_storage_hex(amount)
            }
        }
    }


def _allowance_only_override(
    token: str,
    holder: str,
    spender: str,
    amount: int,
    allowance_mapping_slot: int,
    *,
    layout: Layout = "solidity",
) -> dict[str, Any]:
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    return {
        token_c: {
            "stateDiff": {
                allowance_storage_slot(
                    holder_c,
                    spender_c,
                    allowance_mapping_slot,
                    layout=layout,
                ): to_storage_hex(amount)
            }
        }
    }


def validate_erc20_override(
    w3: Web3,
    token: str,
    *,
    holder: str,
    spender: str,
    amount: int,
    state_override: dict[str, Any],
    block: int | str | None = None,
) -> bool:
    """Return True if overridden ``balanceOf`` / ``allowance`` equal ``amount``."""
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    contract = _erc20(w3, token_c)
    block_id = "latest" if block is None else block
    try:
        bal = int(
            contract.functions.balanceOf(holder_c).call(
                block_identifier=block_id,
                state_override=state_override,
            )
        )
        allow = int(
            contract.functions.allowance(holder_c, spender_c).call(
                block_identifier=block_id,
                state_override=state_override,
            )
        )
    except Exception:
        return False
    return bal == amount and allow == amount


def _find_balance_slot(
    w3: Web3,
    token: str,
    *,
    holder: str,
    amount: int,
    block: int | str | None,
    slots: tuple[int, ...],
    layout: Layout,
) -> int | None:
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    contract = _erc20(w3, token_c)
    block_id = "latest" if block is None else block
    for slot in slots:
        overrides = _balance_only_override(
            token_c, holder_c, amount, slot, layout=layout
        )
        try:
            bal = int(
                contract.functions.balanceOf(holder_c).call(
                    block_identifier=block_id,
                    state_override=overrides,
                )
            )
        except Exception:
            continue
        if bal == amount:
            return slot
    return None


def _find_allowance_slot(
    w3: Web3,
    token: str,
    *,
    holder: str,
    spender: str,
    amount: int,
    block: int | str | None,
    slots: tuple[int, ...],
    layout: Layout,
) -> int | None:
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    contract = _erc20(w3, token_c)
    block_id = "latest" if block is None else block
    for slot in slots:
        overrides = _allowance_only_override(
            token_c,
            holder_c,
            spender_c,
            amount,
            slot,
            layout=layout,
        )
        try:
            allow = int(
                contract.functions.allowance(holder_c, spender_c).call(
                    block_identifier=block_id,
                    state_override=overrides,
                )
            )
        except Exception:
            continue
        if allow == amount:
            return slot
    return None


def _access_list_keys(
    w3: Web3,
    token: str,
    data: str,
    block: int | str | None,
) -> list[str]:
    token_c = checksum_address(token)
    block_id: int | str
    if block is None:
        block_id = "latest"
    elif isinstance(block, int):
        block_id = hex(block)
    else:
        block_id = block
    try:
        resp = w3.provider.make_request(
            RPCEndpoint("eth_createAccessList"),
            [{"to": token_c, "data": data}, block_id],
        )
    except Exception:
        return []
    if not isinstance(resp, dict) or "error" in resp:
        return []
    keys: list[str] = []
    for entry in resp.get("result", {}).get("accessList", []):
        if str(entry.get("address", "")).lower() == token_c.lower():
            keys.extend(entry.get("storageKeys") or [])
    return keys


def _discover_via_access_list(
    w3: Web3,
    token: str,
    *,
    holder: str,
    spender: str,
    amount: int,
    block: int | str | None,
) -> tuple[str, str] | None:
    """Return ``(balance_key, allowance_key)`` using ``eth_createAccessList``."""
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    contract = _erc20(w3, token_c)
    block_id = "latest" if block is None else block

    bal_data = contract.encode_abi("balanceOf", args=[holder_c])
    allow_data = contract.encode_abi("allowance", args=[holder_c, spender_c])
    bal_keys = _access_list_keys(w3, token_c, bal_data, block)
    allow_keys = _access_list_keys(w3, token_c, allow_data, block)
    if not bal_keys or not allow_keys:
        return None

    bal_key: str | None = None
    for key in bal_keys:
        ov = {token_c: {"stateDiff": {key: to_storage_hex(amount)}}}
        try:
            bal = int(
                contract.functions.balanceOf(holder_c).call(
                    block_identifier=block_id,
                    state_override=ov,
                )
            )
        except Exception:
            continue
        if bal == amount:
            bal_key = key
            break
    if bal_key is None:
        return None

    allow_key: str | None = None
    for key in allow_keys:
        ov = {token_c: {"stateDiff": {key: to_storage_hex(amount)}}}
        try:
            allow = int(
                contract.functions.allowance(holder_c, spender_c).call(
                    block_identifier=block_id,
                    state_override=ov,
                )
            )
        except Exception:
            continue
        if allow == amount:
            allow_key = key
            break
    if allow_key is None:
        return None
    return bal_key, allow_key


def _overrides_from_cache(
    token: str,
    holder: str,
    spender: str,
    amount: int,
    cached: dict[str, Any],
) -> dict[str, Any]:
    if cached.get("mode") == "raw":
        return build_override_from_keys(
            token,
            balance_key=cached["bal_key"],
            allowance_key=cached["allow_key"],
            amount=amount,
        )
    return build_erc20_state_override(
        token,
        holder=holder,
        spender=spender,
        amount=amount,
        balance_mapping_slot=int(cached["bal_slot"]),
        allowance_mapping_slot=int(cached["allow_slot"]),
        layout=cached.get("layout", "solidity"),
    )


def probe_erc20_overrides(
    w3: Web3,
    token: str,
    *,
    holder: str,
    spender: str,
    amount: int,
    block: int | str | None = None,
    balance_slots: tuple[int, ...] = MAPPING_SLOTS,
) -> dict[str, Any]:
    """Find a validated ERC-20 state override for ``holder`` / ``spender``."""
    token_c = checksum_address(token)
    holder_c = checksum_address(holder)
    spender_c = checksum_address(spender)
    cache_key = (token_c, holder_c, spender_c)

    cached = _SLOT_CACHE.get(cache_key)
    if cached is not None:
        overrides = _overrides_from_cache(
            token_c, holder_c, spender_c, amount, cached
        )
        if validate_erc20_override(
            w3,
            token_c,
            holder=holder_c,
            spender=spender_c,
            amount=amount,
            state_override=overrides,
            block=block,
        ):
            return overrides
        _SLOT_CACHE.pop(cache_key, None)

    for layout in ("solidity", "vyper"):
        bal_slot = _find_balance_slot(
            w3,
            token_c,
            holder=holder_c,
            amount=amount,
            block=block,
            slots=balance_slots,
            layout=layout,  # type: ignore[arg-type]
        )
        if bal_slot is None:
            continue
        allow_slot = _find_allowance_slot(
            w3,
            token_c,
            holder=holder_c,
            spender=spender_c,
            amount=amount,
            block=block,
            slots=balance_slots,
            layout=layout,  # type: ignore[arg-type]
        )
        if allow_slot is None:
            continue
        overrides = build_erc20_state_override(
            token_c,
            holder=holder_c,
            spender=spender_c,
            amount=amount,
            balance_mapping_slot=bal_slot,
            allowance_mapping_slot=allow_slot,
            layout=layout,  # type: ignore[arg-type]
        )
        if validate_erc20_override(
            w3,
            token_c,
            holder=holder_c,
            spender=spender_c,
            amount=amount,
            state_override=overrides,
            block=block,
        ):
            _SLOT_CACHE[cache_key] = {
                "mode": "slots",
                "layout": layout,
                "bal_slot": bal_slot,
                "allow_slot": allow_slot,
            }
            return overrides

    raw = _discover_via_access_list(
        w3,
        token_c,
        holder=holder_c,
        spender=spender_c,
        amount=amount,
        block=block,
    )
    if raw is not None:
        bal_key, allow_key = raw
        overrides = build_override_from_keys(
            token_c,
            balance_key=bal_key,
            allowance_key=allow_key,
            amount=amount,
        )
        if validate_erc20_override(
            w3,
            token_c,
            holder=holder_c,
            spender=spender_c,
            amount=amount,
            state_override=overrides,
            block=block,
        ):
            _SLOT_CACHE[cache_key] = {
                "mode": "raw",
                "bal_key": bal_key,
                "allow_key": allow_key,
            }
            return overrides

    raise RuntimeError(
        f"Could not build a valid ERC-20 state override for {token_c} "
        f"(holder={holder_c}, spender={spender_c}, amount={amount}). "
        f"Tried Solidity/Vyper mapping slots {list(balance_slots)[:20]}… "
        "and eth_createAccessList. Token may use a non-standard storage layout."
    )


def clear_slot_cache() -> None:
    """Clear the discovered ERC-20 mapping-slot cache (tests / re-probe)."""
    _SLOT_CACHE.clear()
