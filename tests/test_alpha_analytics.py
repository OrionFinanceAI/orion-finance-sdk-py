"""Tests for vault-vs-benchmark relative measures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from orion_finance_sdk_py.stats.benchmark import (
    active_returns,
    benchmark_relative,
    compare_to_benchmark,
)
from orion_finance_sdk_py.stats.series import ReturnSeries


def _daily_index(n: int, start: str = "2024-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="D", tz="UTC")


def test_benchmark_relative_and_compare() -> None:
    idx = _daily_index(60)
    rng = np.random.default_rng(1)
    bench = 0.001 + 0.02 * rng.normal(size=60)
    vault = 0.0002 + 0.8 * bench + 0.005 * rng.normal(size=60)
    prices = pd.DataFrame(
        {
            "CHM": 100 * np.cumprod(1.0 + vault),
            "WBTC": 100 * np.cumprod(1.0 + bench),
        },
        index=idx,
    )
    rs = ReturnSeries.from_prices(prices)
    active = active_returns(rs, "CHM", "WBTC")
    assert active.name == "active"
    assert active.dropna().shape[0] > 50

    rel = benchmark_relative(rs, "CHM", "WBTC", rfr=0.04)
    assert rel["n_obs"] > 50
    assert np.isfinite(rel["tracking_error"])
    assert np.isfinite(rel["information_ratio"])
    assert rel["beta"] == pytest.approx(0.8, abs=0.25)

    table = compare_to_benchmark(rs, "CHM", "WBTC", rfr=0.04)
    assert list(table.index) == ["CHM", "WBTC", "relative"]
    assert "sharpe" in table.columns
    assert np.isfinite(table.loc["relative", "information_ratio"])
