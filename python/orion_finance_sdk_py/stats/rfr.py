"""Protocol risk-free rate helpers and excess-return construction."""

from __future__ import annotations

import pandas as pd

from orion_finance_sdk_py.stats.constants import (
    BPS_PER_UNIT,
    DEFAULT_PERIODS_PER_YEAR,
)


def rfr_decimal(bps: float | int) -> float:
    """Convert an annualized protocol rate in basis points to a decimal.

    ``OrionConfig.risk_free_rate`` is annualized basis points (``410`` →
    ``0.041``).
    """
    return float(bps) / BPS_PER_UNIT


def daily_rfr(
    rfr: float,
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float:
    """Compounded per-period risk-free rate from an annualized decimal ``rfr``.

    ``(1 + rfr) ** (1 / periods_per_year) - 1``.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    return (1.0 + float(rfr)) ** (1.0 / float(periods_per_year)) - 1.0


def excess_returns(
    returns: pd.DataFrame | pd.Series,
    rfr: float,
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> pd.DataFrame:
    """Subtract the compounded per-period risk-free rate from simple returns."""
    rf = daily_rfr(rfr, periods_per_year=periods_per_year)
    frame = returns.to_frame() if isinstance(returns, pd.Series) else returns
    return frame - rf
