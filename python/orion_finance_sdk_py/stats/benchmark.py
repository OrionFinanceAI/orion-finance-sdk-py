"""Benchmark-relative return statistics (IR, alpha/beta, capture ratios)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from orion_finance_sdk_py.stats.measures import summary
from orion_finance_sdk_py.stats.rfr import daily_rfr
from orion_finance_sdk_py.stats.series import ReturnSeries


def _finite_pair(a: pd.Series, b: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Align two series and drop non-finite pairs."""
    frame = pd.concat([a, b], axis=1).dropna()
    if frame.empty:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    x = np.asarray(frame.iloc[:, 0], dtype=float)
    y = np.asarray(frame.iloc[:, 1], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def _path_max_drawdown(prices: pd.Series) -> float:
    """Maximum drawdown on a wealth path (including gaps)."""
    from skfolio.measures import get_drawdowns, max_drawdown

    valid = prices.dropna()
    if len(valid) < 2:
        return float("nan")
    simple = valid.pct_change(fill_method=None).dropna()
    if simple.empty:
        return float("nan")
    drawdowns = get_drawdowns(np.asarray(simple, dtype=float), compounded=True)
    return float(max_drawdown(drawdowns))


def active_returns(
    rs: ReturnSeries,
    vault_col: str,
    benchmark_col: str,
) -> pd.Series:
    """Daily active simple returns ``r_vault - r_benchmark``."""
    if vault_col not in rs.columns or benchmark_col not in rs.columns:
        raise KeyError(
            f"columns {vault_col!r} and {benchmark_col!r} must be in ReturnSeries"
        )
    return (rs.returns[vault_col] - rs.returns[benchmark_col]).rename("active")


def benchmark_relative(
    rs: ReturnSeries,
    vault_col: str,
    benchmark_col: str,
    rfr: float = 0.0,
    *,
    periods_per_year: int | None = None,
) -> pd.Series:
    """Scalar benchmark-relative metrics for one vault vs one benchmark column.

    Returns a Series with ``tracking_error``, ``information_ratio``, ``beta``,
    ``alpha`` (Jensen, annualized), ``upside_capture``, ``downside_capture``,
    ``relative_max_drawdown``, and ``n_obs``.
    """
    ppy = rs.periods_per_year if periods_per_year is None else periods_per_year
    sqrt_ppy = np.sqrt(float(ppy))
    rf_period = daily_rfr(rfr, periods_per_year=ppy)

    active = active_returns(rs, vault_col, benchmark_col)
    act_vals = np.asarray(active.dropna(), dtype=float)
    act_vals = act_vals[np.isfinite(act_vals)]
    n = int(act_vals.size)

    out: dict[str, float] = {"n_obs": float(n)}
    if n < 2:
        for key in (
            "tracking_error",
            "information_ratio",
            "beta",
            "alpha",
            "upside_capture",
            "downside_capture",
            "relative_max_drawdown",
        ):
            out[key] = float("nan")
        return pd.Series(out, dtype=float)

    te = float(np.std(act_vals, ddof=1)) * sqrt_ppy
    out["tracking_error"] = te
    mu_act = float(np.mean(act_vals))
    out["information_ratio"] = (
        (mu_act * ppy) / te if te > 0.0 else float("nan")
    )

    v_ex = rs.returns[vault_col] - rf_period
    b_ex = rs.returns[benchmark_col] - rf_period
    y, x = _finite_pair(v_ex, b_ex)
    if y.size < 2 or float(np.var(x, ddof=1)) <= 0.0:
        out["beta"] = float("nan")
        out["alpha"] = float("nan")
    else:
        # OLS: y = alpha_d + beta * x
        x_mean = float(np.mean(x))
        y_mean = float(np.mean(y))
        cov_xy = float(np.mean((x - x_mean) * (y - y_mean)))
        var_x = float(np.mean((x - x_mean) ** 2))
        beta = cov_xy / var_x
        alpha_d = y_mean - beta * x_mean
        out["beta"] = beta
        out["alpha"] = alpha_d * ppy

    v_ret = rs.returns[vault_col]
    b_ret = rs.returns[benchmark_col]
    pair = pd.concat([v_ret, b_ret], axis=1, keys=["v", "b"]).dropna()
    up = pair[pair["b"] > 0.0]
    down = pair[pair["b"] < 0.0]
    if not up.empty and float(up["b"].sum()) != 0.0:
        out["upside_capture"] = float(up["v"].sum() / up["b"].sum())
    else:
        out["upside_capture"] = float("nan")
    if not down.empty and float(down["b"].sum()) != 0.0:
        out["downside_capture"] = float(down["v"].sum() / down["b"].sum())
    else:
        out["downside_capture"] = float("nan")

    if rs.prices is not None and vault_col in rs.prices and benchmark_col in rs.prices:
        v_dd = _path_max_drawdown(rs.prices[vault_col])
        b_dd = _path_max_drawdown(rs.prices[benchmark_col])
        out["relative_max_drawdown"] = v_dd - b_dd
    else:
        out["relative_max_drawdown"] = float("nan")

    return pd.Series(out, dtype=float)


def compare_to_benchmark(
    rs: ReturnSeries,
    vault_col: str,
    benchmark_col: str,
    rfr: float = 0.0,
    *,
    periods_per_year: int | None = None,
) -> pd.DataFrame:
    """Side-by-side ``summary`` rows plus a ``relative`` row of IR/alpha/beta.

    Index: ``[vault_col, benchmark_col, "relative"]``. Path stats come from
    ``measures.summary``; the relative row holds benchmark-relative scalars
    (NaN for summary-only columns).
    """
    ppy = rs.periods_per_year if periods_per_year is None else periods_per_year
    table = summary(rs, rfr, periods_per_year=ppy)
    if vault_col not in table.index or benchmark_col not in table.index:
        raise KeyError(
            f"summary missing {vault_col!r} or {benchmark_col!r}; "
            f"have {list(table.index)}"
        )
    side = table.loc[[vault_col, benchmark_col]].copy()
    rel = benchmark_relative(
        rs, vault_col, benchmark_col, rfr, periods_per_year=ppy
    )
    for key in rel.index:
        if key not in side.columns:
            side[key] = float("nan")
    rel_row = {col: float("nan") for col in side.columns}
    for key, value in rel.items():
        rel_row[str(key)] = float(value)
    side.loc["relative"] = pd.Series(rel_row)
    return side
