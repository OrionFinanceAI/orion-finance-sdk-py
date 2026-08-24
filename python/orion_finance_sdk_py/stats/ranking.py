"""Orion product ranking: distribution-adjusted then statistically adjusted Sharpe.

SASR is the only ranking score. This module does not compute Probabilistic Sharpe
Ratio, MinTRL, or Deflated Sharpe. Moments used for Bailey's ``vSr`` are
population (``n`` in the denominator); sample Sharpe uses Bessel-corrected std.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from skfolio.measures import fourth_central_moment, third_central_moment

from orion_finance_sdk_py.stats.constants import (
    DEFAULT_PERIODS_PER_YEAR,
    TRACK_RECORD_FULL_TRUST_WEEKS,
)
from orion_finance_sdk_py.stats.rfr import daily_rfr
from orion_finance_sdk_py.stats.series import ReturnSeries


@dataclass(frozen=True)
class RankingMetrics:
    """Univariate ranking intermediates for one return series."""

    n: int
    sample_sharpe: float | None
    dasr: float | None
    sasr: float | None
    t_eff: float | None
    t_weeks: float | None
    w: float | None
    vsr: float | None
    rho: float | None
    sr_daily: float | None
    vol: float | None


def _lag1_autocorr(values: np.ndarray) -> float:
    """Sample lag-1 autocorrelation; 0 if ``n < 3`` or zero variance."""
    n = values.size
    if n < 3:
        return 0.0
    if float(np.std(values, ddof=1)) == 0.0:
        return 0.0
    lagged = values[:-1]
    lead = values[1:]
    if float(np.std(lagged, ddof=1)) == 0.0 or float(np.std(lead, ddof=1)) == 0.0:
        return 0.0
    corr = np.corrcoef(lagged, lead)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)


def _empty_metrics(n: int) -> RankingMetrics:
    """Ranking fields when the series cannot be scored."""
    return RankingMetrics(
        n=n,
        sample_sharpe=None,
        dasr=None,
        sasr=None,
        t_eff=None,
        t_weeks=None,
        w=None,
        vsr=None,
        rho=None,
        sr_daily=None,
        vol=None,
    )


def rank_column(
    returns: pd.Series,
    rfr: float,
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> RankingMetrics:
    """Compute SASR and intermediates for one contiguous daily return series."""
    values = np.asarray(returns.dropna(), dtype=float)
    values = values[np.isfinite(values)]
    n = int(values.size)
    if n < 2:
        return _empty_metrics(n)
    sd = float(np.std(values, ddof=1))
    if sd == 0.0:
        return _empty_metrics(n)

    ppy = float(periods_per_year)
    mean_r = float(np.mean(values))
    sr_daily = (mean_r - daily_rfr(rfr, periods_per_year=periods_per_year)) / sd
    sample_sharpe = sr_daily * np.sqrt(ppy)
    vol = sd * np.sqrt(ppy)

    m2 = float(np.mean((values - mean_r) ** 2))
    if n < 3 or m2 == 0.0:
        skew = 0.0
    else:
        m3 = float(third_central_moment(values))
        skew = m3 / (m2**1.5)

    if n < 4 or m2 == 0.0:
        excess_kurtosis = 0.0
    else:
        m4 = float(fourth_central_moment(values))
        excess_kurtosis = m4 / (m2**2) - 3.0
    kurt_full = excess_kurtosis + 3.0

    vsr = 1.0 - skew * sr_daily + ((kurt_full - 1.0) / 4.0) * sr_daily**2
    rho = _lag1_autocorr(values)
    lo_factor = max(1.0 + 2.0 * rho, 1e-6)
    t_eff = n / lo_factor
    t_weeks = t_eff / 7.0

    dasr: float | None = None
    sasr: float | None = None
    w: float | None = None
    if vsr > 0.0:
        dasr = (sr_daily / np.sqrt(vsr)) * np.sqrt(ppy)
        w = min(1.0, max(0.0, t_weeks / TRACK_RECORD_FULL_TRUST_WEEKS))
        sasr = dasr * w

    return RankingMetrics(
        n=n,
        sample_sharpe=float(sample_sharpe),
        dasr=None if dasr is None else float(dasr),
        sasr=None if sasr is None else float(sasr),
        t_eff=float(t_eff),
        t_weeks=float(t_weeks),
        w=None if w is None else float(w),
        vsr=float(vsr),
        rho=float(rho),
        sr_daily=float(sr_daily),
        vol=float(vol),
    )


def ranking_metrics(
    rs: ReturnSeries,
    rfr: float,
    *,
    periods_per_year: int | None = None,
) -> dict[str, RankingMetrics]:
    """Univariate SASR intermediates for each column of ``rs``."""
    ppy = rs.periods_per_year if periods_per_year is None else periods_per_year
    return {
        str(col): rank_column(rs.returns[col], rfr, periods_per_year=ppy)
        for col in rs.columns
    }


def rank_products(
    rs: ReturnSeries,
    rfr: float,
    *,
    periods_per_year: int | None = None,
) -> pd.Series:
    """SASR by asset, sorted descending. This is the only product ranking score."""
    metrics = ranking_metrics(rs, rfr, periods_per_year=periods_per_year)
    scores = pd.Series(
        {name: item.sasr for name, item in metrics.items()},
        dtype=float,
        name="sasr",
    )
    return scores.sort_values(ascending=False, na_position="last")


def expanding_sasr(
    rs: ReturnSeries,
    rfr: float,
    *,
    periods_per_year: int | None = None,
) -> pd.DataFrame:
    """SASR at each date using all contiguous daily returns up to that date.

    Expanding window (not rolling): column ``j`` at row ``i`` is
    ``rank_column`` on the positional prefix ``rs.returns[j].iloc[: i + 1]``.
    Matches SASR's track-record weight growing with history.
    """
    ppy = rs.periods_per_year if periods_per_year is None else periods_per_year
    returns = rs.returns
    rows: list[dict[str, float]] = []
    for i in range(len(returns.index)):
        row: dict[str, float] = {}
        prefix = returns.iloc[: i + 1]
        for col in returns.columns:
            metrics = rank_column(prefix[col], rfr, periods_per_year=ppy)
            row[str(col)] = (
                float("nan") if metrics.sasr is None else float(metrics.sasr)
            )
        rows.append(row)
    return pd.DataFrame(rows, index=returns.index)
