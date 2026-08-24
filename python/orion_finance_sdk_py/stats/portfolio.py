"""Thin skfolio MeanRisk helpers for research notebooks.

Not a sklearn Pipeline. Weights are labeled Series. Annualization defaults to
365. Zero-variance assets are dropped before fitting, as in the universe
notebook.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from skfolio import RiskMeasure
from skfolio.optimization import MeanRisk, ObjectiveFunction

from orion_finance_sdk_py.stats.constants import DEFAULT_PERIODS_PER_YEAR, ZERO_VARIANCE
from orion_finance_sdk_py.stats.rfr import daily_rfr
from orion_finance_sdk_py.stats.series import ReturnSeries


@dataclass
class FittedPortfolio:
    """Labeled MeanRisk weights plus the fitted skfolio estimator."""

    weights: pd.Series
    model: MeanRisk
    dropped: tuple[str, ...]

    def predict(self, returns: pd.DataFrame) -> object:
        """Predict an out-of-sample skfolio Portfolio on the kept columns."""
        kept = [name for name in self.weights.index if name in returns.columns]
        return self.model.predict(returns.loc[:, kept])


def _as_frame(returns: ReturnSeries | pd.DataFrame) -> pd.DataFrame:
    """Contiguous daily returns as a DataFrame."""
    return returns.returns if isinstance(returns, ReturnSeries) else returns


def chronological_split(
    returns: ReturnSeries | pd.DataFrame,
    test_size: float = 0.33,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-ordered train/test split (no shuffle) on overlapping rows."""
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be in (0, 1)")
    overlap = _as_frame(returns).dropna(how="any")
    n = len(overlap)
    n_test = int(round(n * test_size))
    n_train = n - n_test
    if n_train < 1 or n_test < 1:
        raise ValueError("split would leave an empty train or test set")
    return overlap.iloc[:n_train], overlap.iloc[n_train:]


def drop_zero_variance(
    returns: pd.DataFrame,
    *,
    threshold: float = ZERO_VARIANCE,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Drop columns whose population std is at or below ``threshold``."""
    vol = returns.std(ddof=0)
    dropped = tuple(str(name) for name in vol.index[vol <= threshold])
    if dropped:
        returns = returns.drop(columns=list(dropped))
    return returns, dropped


def _fit_mean_risk(
    returns: pd.DataFrame,
    model: MeanRisk,
    dropped: tuple[str, ...],
) -> FittedPortfolio:
    """Fit ``model`` and wrap labeled weights."""
    if returns.shape[1] < 2 or returns.shape[0] < 2:
        raise ValueError("MeanRisk needs at least 2 assets and 2 observations")
    model.fit(returns)
    weights = pd.Series(model.weights_, index=returns.columns, dtype=float)
    return FittedPortfolio(weights=weights, model=model, dropped=dropped)


def _prepare(
    returns: ReturnSeries | pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Overlap rows and drop flat assets."""
    overlap = _as_frame(returns).dropna(how="any")
    return drop_zero_variance(overlap)


def min_variance(
    returns: ReturnSeries | pd.DataFrame,
    *,
    rfr: float = 0.0,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> FittedPortfolio:
    """Minimum-variance long-only portfolio (skfolio ``MeanRisk`` default)."""
    frame, dropped = _prepare(returns)
    rf_period = daily_rfr(rfr, periods_per_year=periods_per_year)
    model = MeanRisk(
        risk_free_rate=rf_period,
        portfolio_params={"annualized_factor": float(periods_per_year)},
    )
    return _fit_mean_risk(frame, model, dropped)


def max_sortino(
    returns: ReturnSeries | pd.DataFrame,
    *,
    rfr: float = 0.0,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> FittedPortfolio:
    """Maximize Sortino ratio (mean / semi-deviation)."""
    frame, dropped = _prepare(returns)
    rf_period = daily_rfr(rfr, periods_per_year=periods_per_year)
    model = MeanRisk(
        objective_function=ObjectiveFunction.MAXIMIZE_RATIO,
        risk_measure=RiskMeasure.SEMI_VARIANCE,
        risk_free_rate=rf_period,
        portfolio_params={"annualized_factor": float(periods_per_year)},
    )
    return _fit_mean_risk(frame, model, dropped)


def max_sharpe(
    returns: ReturnSeries | pd.DataFrame,
    *,
    rfr: float = 0.0,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> FittedPortfolio:
    """Maximize Sharpe ratio (mean / variance)."""
    frame, dropped = _prepare(returns)
    rf_period = daily_rfr(rfr, periods_per_year=periods_per_year)
    model = MeanRisk(
        objective_function=ObjectiveFunction.MAXIMIZE_RATIO,
        risk_measure=RiskMeasure.VARIANCE,
        risk_free_rate=rf_period,
        portfolio_params={"annualized_factor": float(periods_per_year)},
    )
    return _fit_mean_risk(frame, model, dropped)
