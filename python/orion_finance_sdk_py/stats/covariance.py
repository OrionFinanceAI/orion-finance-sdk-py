"""skfolio-backed covariance and correlation estimators."""

from __future__ import annotations

import numpy as np
import pandas as pd
from skfolio.measures import correlation as skfolio_correlation
from skfolio.moments import EmpiricalCovariance, LedoitWolf

from orion_finance_sdk_py.stats.series import ReturnSeries


def _overlapping_returns(rs: ReturnSeries | pd.DataFrame) -> pd.DataFrame:
    """Contiguous daily returns with rows that are complete across assets."""
    frame = rs.returns if isinstance(rs, ReturnSeries) else rs
    overlap = frame.dropna(how="any")
    if overlap.empty:
        raise ValueError("no overlapping contiguous daily returns")
    return overlap


def _labeled_square(matrix: np.ndarray, columns: pd.Index) -> pd.DataFrame:
    """Wrap a square numpy matrix with asset labels."""
    return pd.DataFrame(matrix, index=columns, columns=columns)


def sample(rs: ReturnSeries | pd.DataFrame) -> pd.DataFrame:
    """Sample covariance via skfolio ``EmpiricalCovariance`` (``ddof=1``)."""
    overlap = _overlapping_returns(rs)
    model = EmpiricalCovariance(ddof=1)
    model.fit(overlap)
    return _labeled_square(np.asarray(model.covariance_), overlap.columns)


def ledoit_wolf(rs: ReturnSeries | pd.DataFrame) -> pd.DataFrame:
    """Ledoit–Wolf shrunk covariance via skfolio ``LedoitWolf``."""
    overlap = _overlapping_returns(rs)
    model = LedoitWolf()
    model.fit(overlap)
    return _labeled_square(np.asarray(model.covariance_), overlap.columns)


def correlation(rs: ReturnSeries | pd.DataFrame) -> pd.DataFrame:
    """Correlation of overlapping contiguous daily returns (skfolio)."""
    overlap = _overlapping_returns(rs)
    matrix = np.asarray(skfolio_correlation(overlap.to_numpy(dtype=float)))
    return _labeled_square(matrix, overlap.columns)
