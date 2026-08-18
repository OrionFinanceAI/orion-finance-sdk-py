"""TickMath port from @uniswap/v3-core."""

from __future__ import annotations

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
)


def get_sqrt_ratio_at_tick(tick: int) -> int:
    """Return the sqrt price as a Q64.96 for ``tick``."""
    if tick < MIN_TICK or tick > MAX_TICK:
        raise ValueError(f"tick {tick} out of bounds")

    abs_tick = -tick if tick < 0 else tick
    ratio = (
        0xFFFCB933BD6FAD37AA2D162D1A594001
        if abs_tick & 0x1
        else 0x100000000000000000000000000000000
    )

    masks = [
        (0x2, 0xFFF97272373D413259A46990580E213A),
        (0x4, 0xFFF2E50F5F656932EF12357CF3C7FDCC),
        (0x8, 0xFFE5CACA7E10E4E61C3624EAA0941CD0),
        (0x10, 0xFFCB9843D60F6159C9DB58835C926644),
        (0x20, 0xFF973B41FA98C081472E6896DFB254C0),
        (0x40, 0xFF2EA16466C96A3843EC78B326B52861),
        (0x80, 0xFE5DEE046A99A2A811C461F1969C3053),
        (0x100, 0xFCBE86C7900A88AEDCFFC83B479AA3A4),
        (0x200, 0xF987A7253AC413176F2B074CF7815E54),
        (0x400, 0xF3392B0822B70005940C7A398E4B70F3),
        (0x800, 0xE7159475A2C29B7443B29C7FA6E889D9),
        (0x1000, 0xD097F3BDFD2022B8845AD8F792AA5825),
        (0x2000, 0xA9F746462D870FDF8A65DC1F90E061E5),
        (0x4000, 0x70D869A156D2A1B890BB3DF62BAF32F7),
        (0x8000, 0x31BE135F97D08FD981231505542FCFA6),
        (0x10000, 0x9AA508B5B7A84E1C677DE54F3E99BC9),
        (0x20000, 0x5D6AF8DEDB81196699C329225EE604),
        (0x40000, 0x2216E584F5FA1EA926041BEDFE98),
        (0x80000, 0x48A170391F7DC42444E8FA2),
    ]
    for mask, multiplier in masks:
        if abs_tick & mask:
            ratio = (ratio * multiplier) >> 128

    if tick > 0:
        ratio = (2**256 - 1) // ratio

    sqrt_price_x96 = (ratio >> 32) + (1 if ratio % (1 << 32) else 0)
    return int(sqrt_price_x96)


def get_tick_at_sqrt_ratio(sqrt_price_x96: int) -> int:
    """Return the greatest tick whose sqrt ratio is at most ``sqrt_price_x96``."""
    if sqrt_price_x96 < MIN_SQRT_RATIO or sqrt_price_x96 >= MAX_SQRT_RATIO:
        raise ValueError("sqrt price out of bounds")

    lo = MIN_TICK
    hi = MAX_TICK
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if get_sqrt_ratio_at_tick(mid) <= sqrt_price_x96:
            lo = mid
        else:
            hi = mid - 1
    return lo
