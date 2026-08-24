"""skfolio-backed return measures plus Orion ranking fields.

skfolio's Portfolio default annualization is 252 trading days. This module
passes ``periods_per_year=365``. skfolio ``standard_deviation`` defaults to
sample std (``biased=False``), which matches Orion sample Sharpe. Bailey
``vSr`` skew/kurtosis stay population moments in ``ranking``. ``sharpe`` is
not SASR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from skfolio.measures import (
    cvar,
    get_drawdowns,
    max_drawdown,
    semi_deviation,
    standard_deviation,
    value_at_risk,
)
from skfolio.measures import (
    mean as skfolio_mean,
)

from orion_finance_sdk_py.stats.ranking import RankingMetrics, ranking_metrics
from orion_finance_sdk_py.stats.rfr import daily_rfr
from orion_finance_sdk_py.stats.series import ReturnSeries


def _finite(values: pd.Series) -> np.ndarray:
    """Drop NaN/inf from a column."""
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def _path_total_return(prices: pd.Series) -> float:
    """First-to-last simple return on a price path (gaps allowed)."""
    valid = prices.dropna()
    if len(valid) < 2:
        return float("nan")
    first = float(valid.iloc[0])
    last = float(valid.iloc[-1])
    if first == 0.0:
        return float("nan")
    return last / first - 1.0


def _cagr(prices: pd.Series, periods_per_year: int) -> float:
    """Compound annual growth rate from a price path."""
    valid = prices.dropna()
    if len(valid) < 2:
        return float("nan")
    n_days = (valid.index[-1] - valid.index[0]).days
    if n_days <= 0:
        return float("nan")
    total = float(valid.iloc[-1]) / float(valid.iloc[0])
    if total <= 0.0:
        return float("nan")
    return float(total ** (periods_per_year / n_days) - 1.0)


def _path_max_drawdown(prices: pd.Series) -> float:
    """Maximum drawdown on the wealth path, including calendar gaps."""
    valid = prices.dropna()
    if len(valid) < 2:
        return float("nan")
    simple = valid.pct_change(fill_method=None).dropna()
    if simple.empty:
        return float("nan")
    drawdowns = get_drawdowns(np.asarray(simple, dtype=float), compounded=True)
    return float(max_drawdown(drawdowns))


def _period_max_drawdown(returns: np.ndarray) -> float:
    """Maximum drawdown from a contiguous daily return series."""
    if returns.size < 2:
        return float("nan")
    drawdowns = get_drawdowns(returns, compounded=True)
    return float(max_drawdown(drawdowns))


def _ranking_row(metrics: RankingMetrics) -> dict[str, float]:
    """Flatten ranking intermediates into summary columns."""
    return {
        "sample_sharpe": _or_nan(metrics.sample_sharpe),
        "dasr": _or_nan(metrics.dasr),
        "sasr": _or_nan(metrics.sasr),
        "t_eff": _or_nan(metrics.t_eff),
        "t_weeks": _or_nan(metrics.t_weeks),
        "w": _or_nan(metrics.w),
        "vsr": _or_nan(metrics.vsr),
        "rho": _or_nan(metrics.rho),
    }


def _or_nan(value: float | None) -> float:
    """Map ``None`` ranking fields to NaN for DataFrame columns."""
    return float("nan") if value is None else float(value)


def summary(
    rs: ReturnSeries,
    rfr: float = 0.0,
    *,
    periods_per_year: int | None = None,
    cvar_beta: float = 0.95,
    var_beta: float = 0.95,
) -> pd.DataFrame:
    """One row per asset: skfolio period stats, path stats, and SASR fields.

    ``sharpe`` is 365-day sample Sharpe from skfolio mean / sample std. ``sasr``
    is the Orion ranking score. They are not aliases.
    """
    ppy = rs.periods_per_year if periods_per_year is None else periods_per_year
    sqrt_ppy = np.sqrt(float(ppy))
    rf_period = daily_rfr(rfr, periods_per_year=ppy)
    ranks = ranking_metrics(rs, rfr, periods_per_year=ppy)
    prices = rs.prices
    rows: list[dict[str, float | str | int]] = []
    for col in rs.columns:
        name = str(col)
        values = _finite(rs.returns[col])
        n_obs = int(values.size)
        row: dict[str, float | str | int] = {"asset": name, "n_obs": n_obs}
        if n_obs == 0:
            row.update(
                {
                    "mean": float("nan"),
                    "vol": float("nan"),
                    "sharpe": float("nan"),
                    "sortino": float("nan"),
                    "cvar": float("nan"),
                    "var": float("nan"),
                    "max_drawdown": float("nan"),
                    "total_return": float("nan"),
                    "cagr": float("nan"),
                    "total_excess": float("nan"),
                }
            )
        else:
            mu = float(skfolio_mean(values))
            sd = float(standard_deviation(values, biased=False))
            excess = mu - rf_period
            row["mean"] = mu
            row["vol"] = sd * sqrt_ppy if np.isfinite(sd) else float("nan")
            if sd > 0.0:
                row["sharpe"] = (excess / sd) * sqrt_ppy
            else:
                row["sharpe"] = float("nan")
            semi = float(semi_deviation(values, biased=False))
            if semi > 0.0:
                row["sortino"] = (excess / semi) * sqrt_ppy
            else:
                row["sortino"] = float("nan")
            row["cvar"] = float(cvar(values, beta=cvar_beta))
            row["var"] = float(value_at_risk(values, beta=var_beta))
            if prices is not None and name in prices.columns:
                path = prices[name]
                row["max_drawdown"] = _path_max_drawdown(path)
                total = _path_total_return(path)
                row["total_return"] = total
                row["cagr"] = _cagr(path, ppy)
                valid = path.dropna()
                if len(valid) >= 2:
                    n_days = max(1, (valid.index[-1] - valid.index[0]).days)
                    period_rfr = (1.0 + float(rfr)) ** (n_days / float(ppy)) - 1.0
                    row["total_excess"] = total - period_rfr
                else:
                    row["total_excess"] = float("nan")
            else:
                row["max_drawdown"] = _period_max_drawdown(values)
                row["total_return"] = float("nan")
                row["cagr"] = float("nan")
                row["total_excess"] = float("nan")
        row.update(_ranking_row(ranks[name]))
        rows.append(row)
    frame = pd.DataFrame(rows).set_index("asset")
    return frame


def product_scoreboard(
    rs: ReturnSeries,
    rfr: float = 0.0,
    *,
    periods_per_year: int | None = None,
) -> pd.DataFrame:
    """``summary`` sorted by SASR descending (the product ranking table)."""
    table = summary(rs, rfr, periods_per_year=periods_per_year)
    return table.sort_values("sasr", ascending=False, na_position="last")
