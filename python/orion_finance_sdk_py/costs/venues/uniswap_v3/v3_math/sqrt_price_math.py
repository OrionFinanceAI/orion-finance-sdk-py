"""SqrtPriceMath port from @uniswap/v3-core."""

from __future__ import annotations

from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import Q96
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.full_math import (
    div_rounding_up,
    mul_div,
    mul_div_rounding_up,
)


def _sort_sqrt_ratios(sqrt_a: int, sqrt_b: int) -> tuple[int, int]:
    if sqrt_a > sqrt_b:
        return sqrt_b, sqrt_a
    return sqrt_a, sqrt_b


def get_next_sqrt_price_from_amount0_rounding_up(
    sqrt_px96: int, liquidity: int, amount: int, add: bool
) -> int:
    """Return the next sqrt price after an amount0 delta, rounding up."""
    if amount == 0:
        return sqrt_px96
    numerator1 = liquidity << 96
    if add:
        product = amount * sqrt_px96
        if amount != 0 and product // amount == sqrt_px96:
            denominator = numerator1 + product
            if denominator >= numerator1:
                return mul_div_rounding_up(numerator1, sqrt_px96, denominator)
        return div_rounding_up(numerator1, numerator1 // sqrt_px96 + amount)

    product = amount * sqrt_px96
    if amount == 0 or product // amount != sqrt_px96 or numerator1 <= product:
        raise ValueError("invalid amount0 delta")
    denominator = numerator1 - product
    return mul_div_rounding_up(numerator1, sqrt_px96, denominator)


def get_next_sqrt_price_from_amount1_rounding_down(
    sqrt_px96: int, liquidity: int, amount: int, add: bool
) -> int:
    """Return the next sqrt price after an amount1 delta, rounding down."""
    if add:
        quotient = (
            (amount << 96) // liquidity
            if amount <= (1 << 160) - 1
            else mul_div(amount, Q96, liquidity)
        )
        return sqrt_px96 + quotient

    quotient = (
        div_rounding_up(amount << 96, liquidity)
        if amount <= (1 << 160) - 1
        else mul_div_rounding_up(amount, Q96, liquidity)
    )
    if sqrt_px96 <= quotient:
        raise ValueError("sqrt price underflow")
    return sqrt_px96 - quotient


def get_next_sqrt_price_from_input(
    sqrt_px96: int, liquidity: int, amount_in: int, zero_for_one: bool
) -> int:
    """Return the next sqrt price given a token input amount."""
    if sqrt_px96 <= 0 or liquidity <= 0:
        raise ValueError("invalid price or liquidity")
    if zero_for_one:
        return get_next_sqrt_price_from_amount0_rounding_up(
            sqrt_px96, liquidity, amount_in, True
        )
    return get_next_sqrt_price_from_amount1_rounding_down(
        sqrt_px96, liquidity, amount_in, True
    )


def get_next_sqrt_price_from_output(
    sqrt_px96: int, liquidity: int, amount_out: int, zero_for_one: bool
) -> int:
    """Return the next sqrt price given a token output amount."""
    if sqrt_px96 <= 0 or liquidity <= 0:
        raise ValueError("invalid price or liquidity")
    if zero_for_one:
        return get_next_sqrt_price_from_amount1_rounding_down(
            sqrt_px96, liquidity, amount_out, False
        )
    return get_next_sqrt_price_from_amount0_rounding_up(
        sqrt_px96, liquidity, amount_out, False
    )


def get_amount0_delta(
    sqrt_ratio_a: int, sqrt_ratio_b: int, liquidity: int, round_up: bool
) -> int:
    """Return the amount0 delta between two sqrt prices."""
    sqrt_a, sqrt_b = _sort_sqrt_ratios(sqrt_ratio_a, sqrt_ratio_b)
    if sqrt_a <= 0:
        raise ValueError("sqrt ratio must be positive")
    numerator1 = liquidity << 96
    numerator2 = sqrt_b - sqrt_a
    if round_up:
        return div_rounding_up(
            mul_div_rounding_up(numerator1, numerator2, sqrt_b), sqrt_a
        )
    return mul_div(numerator1, numerator2, sqrt_b) // sqrt_a


def get_amount1_delta(
    sqrt_ratio_a: int, sqrt_ratio_b: int, liquidity: int, round_up: bool
) -> int:
    """Return the amount1 delta between two sqrt prices."""
    sqrt_a, sqrt_b = _sort_sqrt_ratios(sqrt_ratio_a, sqrt_ratio_b)
    if round_up:
        return mul_div_rounding_up(liquidity, sqrt_b - sqrt_a, Q96)
    return mul_div(liquidity, sqrt_b - sqrt_a, Q96)
