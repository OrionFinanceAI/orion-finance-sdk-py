"""Unit tests for Uniswap v3 math ported into the SDK."""

import pytest
from orion_finance_sdk_py.costs.venues.uniswap_v3.constants import (
    MAX_SQRT_RATIO,
    MAX_TICK,
    MIN_SQRT_RATIO,
    MIN_TICK,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.sqrt_price_math import (
    get_amount0_delta,
    get_next_sqrt_price_from_amount0_rounding_up,
    get_next_sqrt_price_from_input,
    get_next_sqrt_price_from_output,
)
from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.tick_math import (
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
)


def test_get_sqrt_ratio_at_tick_zero():
    assert get_sqrt_ratio_at_tick(0) == 79228162514264337593543950336


def test_get_sqrt_ratio_at_tick_positive_and_bounds():
    assert get_sqrt_ratio_at_tick(1) > get_sqrt_ratio_at_tick(0)
    with pytest.raises(ValueError, match="out of bounds"):
        get_sqrt_ratio_at_tick(MIN_TICK - 1)
    with pytest.raises(ValueError, match="out of bounds"):
        get_sqrt_ratio_at_tick(MAX_TICK + 1)


def test_get_tick_at_sqrt_ratio_bounds():
    assert get_tick_at_sqrt_ratio(MIN_SQRT_RATIO) == MIN_TICK
    with pytest.raises(ValueError, match="sqrt price out of bounds"):
        get_tick_at_sqrt_ratio(MIN_SQRT_RATIO - 1)
    with pytest.raises(ValueError, match="sqrt price out of bounds"):
        get_tick_at_sqrt_ratio(MAX_SQRT_RATIO)


def test_sqrt_price_math_zero_amount_and_invalid_liquidity():
    px = get_sqrt_ratio_at_tick(0)
    assert get_next_sqrt_price_from_amount0_rounding_up(px, 10**18, 0, True) == px
    with pytest.raises(ValueError, match="invalid price or liquidity"):
        get_next_sqrt_price_from_input(0, 1, 1, True)
    with pytest.raises(ValueError, match="invalid price or liquidity"):
        get_next_sqrt_price_from_output(px, 0, 1, True)


def test_get_amount0_delta_sorts_ratios():
    a = get_sqrt_ratio_at_tick(10)
    b = get_sqrt_ratio_at_tick(0)
    assert get_amount0_delta(a, b, 10**18, False) == get_amount0_delta(
        b, a, 10**18, False
    )
