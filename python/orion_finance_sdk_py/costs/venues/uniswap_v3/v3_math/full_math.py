"""FullMath mulDiv helpers (Uniswap v3-core port)."""

from __future__ import annotations


def mul_div(a: int, b: int, denominator: int) -> int:
    """Return ``(a * b) // denominator`` with Uniswap FullMath semantics."""
    if denominator == 0:
        raise ZeroDivisionError("mul_div denominator is zero")
    return (a * b) // denominator


def mul_div_rounding_up(a: int, b: int, denominator: int) -> int:
    """Return ``mul_div`` rounded up when the remainder is nonzero."""
    result = mul_div(a, b, denominator)
    if (a * b) % denominator > 0:
        result += 1
    return result


def div_rounding_up(numerator: int, denominator: int) -> int:
    """Return ``numerator // denominator`` rounded up on a nonzero remainder."""
    result = numerator // denominator
    if numerator % denominator > 0:
        result += 1
    return result
