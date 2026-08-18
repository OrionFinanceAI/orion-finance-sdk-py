"""Unit tests for Uniswap v3 math ported into the SDK."""

from orion_finance_sdk_py.costs.venues.uniswap_v3.v3_math.tick_math import (
    get_sqrt_ratio_at_tick,
)


def test_get_sqrt_ratio_at_tick_zero():
    assert get_sqrt_ratio_at_tick(0) == 79228162514264337593543950336
