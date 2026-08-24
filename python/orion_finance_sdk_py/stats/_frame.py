"""Shared conversion helpers for return panels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def as_dataframe(
    data: pd.Series | pd.DataFrame, *, default_name: str = "asset"
) -> pd.DataFrame:
    """Coerce a Series or DataFrame of values to a two-dimensional frame."""
    if isinstance(data, pd.Series):
        name = data.name if data.name is not None else default_name
        return data.to_frame(name=name)
    if isinstance(data, pd.DataFrame):
        return data.copy()
    raise TypeError("expected a pandas Series or DataFrame")


def require_datetime_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    """Return the frame index if it is a ``DatetimeIndex``."""
    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("return and price panels require a DatetimeIndex")
    return index


def gap_boundary_mask(index: pd.Index) -> np.ndarray[Any, np.dtype[np.bool_]]:
    """Mark rows whose calendar gap from the previous observation exceeds 1 day."""
    n = len(index)
    mask = np.zeros(n, dtype=bool)
    if n == 0:
        return mask
    days = pd.DatetimeIndex(pd.to_datetime(index, utc=True)).asi8 // 86_400_000_000_000
    mask[1:] = np.diff(days) > 1
    return mask


def mask_gap_boundary_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Set gap-boundary rows to NaN so multi-day jumps are not treated as daily."""
    idx = require_datetime_index(returns)
    out = returns.copy()
    out.loc[gap_boundary_mask(idx)] = np.nan
    return out


def mask_nonpositive_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Replace non-positive prices with NaN."""
    out = prices.copy()
    return out.mask(out <= 0)
