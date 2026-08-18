"""SwapMath port from @uniswap/v3-core."""

from __future__ import annotations

from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.full_math import (
    mul_div,
    mul_div_rounding_up,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.sqrt_price_math import (
    get_amount0_delta,
    get_amount1_delta,
    get_next_sqrt_price_from_input,
    get_next_sqrt_price_from_output,
)


def compute_swap_step(
    sqrt_ratio_current_x96: int,
    sqrt_ratio_target_x96: int,
    liquidity: int,
    amount_remaining: int,
    fee_pips: int,
) -> tuple[int, int, int, int]:
    """Compute one Uniswap v3 swap step until the next tick or remaining amount."""
    zero_for_one = sqrt_ratio_current_x96 >= sqrt_ratio_target_x96
    exact_in = amount_remaining >= 0

    amount_in = 0
    amount_out = 0
    fee_amount = 0

    if exact_in:
        amount_remaining_less_fee = mul_div(
            amount_remaining, 1_000_000 - fee_pips, 1_000_000
        )
        amount_in = (
            get_amount0_delta(
                sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, True
            )
            if zero_for_one
            else get_amount1_delta(
                sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, True
            )
        )
        if amount_remaining_less_fee >= amount_in:
            sqrt_ratio_next_x96 = sqrt_ratio_target_x96
        else:
            sqrt_ratio_next_x96 = get_next_sqrt_price_from_input(
                sqrt_ratio_current_x96,
                liquidity,
                amount_remaining_less_fee,
                zero_for_one,
            )
    else:
        amount_out = (
            get_amount1_delta(
                sqrt_ratio_target_x96, sqrt_ratio_current_x96, liquidity, False
            )
            if zero_for_one
            else get_amount0_delta(
                sqrt_ratio_current_x96, sqrt_ratio_target_x96, liquidity, False
            )
        )
        remaining_out = -amount_remaining
        if remaining_out >= amount_out:
            sqrt_ratio_next_x96 = sqrt_ratio_target_x96
        else:
            sqrt_ratio_next_x96 = get_next_sqrt_price_from_output(
                sqrt_ratio_current_x96,
                liquidity,
                remaining_out,
                zero_for_one,
            )

    max_reached = sqrt_ratio_target_x96 == sqrt_ratio_next_x96

    if zero_for_one:
        amount_in = (
            amount_in
            if max_reached and exact_in
            else get_amount0_delta(
                sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, True
            )
        )
        amount_out = (
            amount_out
            if max_reached and not exact_in
            else get_amount1_delta(
                sqrt_ratio_next_x96, sqrt_ratio_current_x96, liquidity, False
            )
        )
    else:
        amount_in = (
            amount_in
            if max_reached and exact_in
            else get_amount1_delta(
                sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, True
            )
        )
        amount_out = (
            amount_out
            if max_reached and not exact_in
            else get_amount0_delta(
                sqrt_ratio_current_x96, sqrt_ratio_next_x96, liquidity, False
            )
        )

    if not exact_in and amount_out > -amount_remaining:
        amount_out = -amount_remaining

    if exact_in and sqrt_ratio_next_x96 != sqrt_ratio_target_x96:
        fee_amount = amount_remaining - amount_in
    else:
        fee_amount = mul_div_rounding_up(amount_in, fee_pips, 1_000_000 - fee_pips)

    return sqrt_ratio_next_x96, amount_in, amount_out, fee_amount
