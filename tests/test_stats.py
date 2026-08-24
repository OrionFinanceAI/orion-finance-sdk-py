"""Tests for return-series hygiene, SASR ranking, and skfolio wrappers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from orion_finance_sdk_py import ReturnSeries, covariance, measures, rank_products
from orion_finance_sdk_py.stats.constants import TRACK_RECORD_FULL_TRUST_WEEKS
from orion_finance_sdk_py.stats.factors import pca
from orion_finance_sdk_py.stats.panels import (
    from_price_history,
    from_share_price_histories,
    normalized_prices,
)
from orion_finance_sdk_py.stats.portfolio import chronological_split, min_variance
from orion_finance_sdk_py.stats.ranking import (
    expanding_sasr,
    rank_column,
    ranking_metrics,
)
from orion_finance_sdk_py.stats.rfr import daily_rfr, rfr_decimal

RFR = 0.041


def _daily_index(n: int, start: str = "2024-01-01") -> pd.DatetimeIndex:
    """UTC calendar-day index of length ``n``."""
    return pd.date_range(start, periods=n, freq="D", tz="UTC")


def _from_array(values: np.ndarray, name: str = "a") -> ReturnSeries:
    """ReturnSeries from a 1-d numpy array of daily simple returns."""
    series = pd.Series(values, index=_daily_index(len(values)), name=name)
    return ReturnSeries.from_returns(series)


def test_rfr_decimal_is_compounded_daily() -> None:
    """Protocol bps convert to decimal; daily RFR is compounded."""
    assert rfr_decimal(410) == pytest.approx(0.041)
    assert daily_rfr(RFR) == pytest.approx((1.0 + RFR) ** (1.0 / 365.0) - 1.0)
    assert daily_rfr(RFR) != pytest.approx(RFR / 365)


def test_short_track_confidence_scales_sasr() -> None:
    """~30 iid days: w ≈ (n/7)/26 and sasr ≈ dasr * w < dasr."""
    rng = np.random.default_rng(0)
    values = 0.02 + 0.005 * rng.normal(size=30)
    metrics = rank_column(pd.Series(values, index=_daily_index(30)), RFR)
    assert metrics.n == 30
    assert metrics.rho is not None and metrics.rho == pytest.approx(0.0, abs=0.35)
    assert metrics.t_eff is not None
    assert (
        metrics.w is not None and metrics.dasr is not None and metrics.sasr is not None
    )
    expected_w = min(1.0, (metrics.t_eff / 7.0) / TRACK_RECORD_FULL_TRUST_WEEKS)
    assert metrics.w == pytest.approx(expected_w)
    assert metrics.w < 1.0
    assert metrics.sasr == pytest.approx(metrics.dasr * metrics.w)
    assert metrics.sasr < metrics.dasr


def test_long_track_full_confidence() -> None:
    """Long iid track: T_eff >= 182, w = 1, sasr ≈ dasr."""
    rng = np.random.default_rng(1)
    values = 0.0005 + 0.008 * rng.normal(size=220)
    metrics = rank_column(pd.Series(values, index=_daily_index(220)), RFR)
    assert metrics.t_eff is not None and metrics.t_eff >= 182
    assert metrics.w == pytest.approx(1.0)
    assert metrics.sasr == pytest.approx(metrics.dasr)


def test_positive_lag1_lowers_sasr_not_dasr() -> None:
    """Same multiset: blocked (ρ>0) has lower T_eff and SASR; DASR unchanged."""
    positives = np.full(18, 0.02)
    negatives = np.full(18, -0.01)
    blocked = np.concatenate([positives, negatives])
    # Contiguous shuffle of the same values → near-zero lag-1 (not a perfect
    # alternating pattern, which would drive ρ → −1 and make Lo T_eff negative).
    rng = np.random.default_rng(7)
    shuffled = rng.permutation(blocked)
    blocked_m = rank_column(pd.Series(blocked, index=_daily_index(36)), RFR)
    iid_m = rank_column(pd.Series(shuffled, index=_daily_index(36)), RFR)
    assert blocked_m.dasr == pytest.approx(iid_m.dasr)
    assert blocked_m.rho is not None and blocked_m.rho > 0
    assert iid_m.rho is not None and abs(iid_m.rho) < blocked_m.rho
    assert blocked_m.t_eff is not None and iid_m.t_eff is not None
    assert blocked_m.t_eff < iid_m.t_eff
    assert blocked_m.sasr is not None and iid_m.sasr is not None
    assert blocked_m.sasr < iid_m.sasr


def test_too_few_obs_and_zero_vol_are_none() -> None:
    """n < 2 or zero sample vol → ranking fields are None."""
    one = rank_column(pd.Series([0.01], index=_daily_index(1)), RFR)
    assert one.n == 1
    assert one.sasr is None and one.sample_sharpe is None
    flat = rank_column(pd.Series([0.01, 0.01, 0.01], index=_daily_index(3)), RFR)
    assert flat.sasr is None and flat.sample_sharpe is None


def test_gap_boundary_return_dropped() -> None:
    """A 3-day calendar hole drops only the jump; SASR matches the kept days."""
    idx = pd.to_datetime(
        [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-07",
            "2024-01-08",
            "2024-01-09",
        ],
        utc=True,
    )
    prices = pd.Series(
        [100.0, 101.0, 102.0, 103.0, 120.0, 121.0, 122.0],
        index=idx,
        name="vault",
    )
    gappy = ReturnSeries.from_prices(prices)
    kept = gappy.returns["vault"].dropna()
    assert pd.Timestamp("2024-01-07", tz="UTC") not in kept.index
    assert len(kept) == 5
    naive = prices.pct_change(fill_method=None).dropna()
    assert pd.Timestamp("2024-01-07", tz="UTC") in naive.index
    from_kept = ReturnSeries.from_returns(
        pd.Series(kept.to_numpy(), index=_daily_index(len(kept)), name="vault")
    )
    gappy_m = ranking_metrics(gappy, RFR)["vault"]
    kept_m = ranking_metrics(from_kept, RFR)["vault"]
    assert gappy_m.sasr == pytest.approx(kept_m.sasr)
    naive_m = rank_column(naive, RFR)
    assert naive_m.sasr != pytest.approx(gappy_m.sasr)


def test_from_price_history_panel() -> None:
    """Adapter history dicts become a labeled UTC price panel."""
    series = [
        {
            "timestamp": 1_704_067_200,
            "block": 1,
            "prices": {"0xabcDEF0000000000000000000000000000000001": 10**14},
        },
        {
            "timestamp": 1_704_153_600,
            "block": 2,
            "prices": {"0xabcDEF0000000000000000000000000000000001": 2 * 10**14},
        },
    ]
    names = {"0xabcDEF0000000000000000000000000000000001": "USDC"}
    prices = from_price_history(series, decimals=14, names=names)
    assert list(prices.columns) == ["USDC"]
    assert prices.iloc[0, 0] == pytest.approx(1.0)
    assert prices.iloc[1, 0] == pytest.approx(2.0)
    assert str(prices.index.tz) == "UTC"
    rs = ReturnSeries.from_price_history(series, decimals=14, names=names)
    assert rs.returns["USDC"].iloc[1] == pytest.approx(1.0)


def test_from_share_price_histories_and_normalized() -> None:
    """Vault histories align on timestamp and rebase to 1.0."""
    histories = {
        "AAA": [
            {"timestamp": 1_704_067_200, "block": 1, "share_price": 100},
            {"timestamp": 1_704_153_600, "block": 2, "share_price": 110},
        ],
        "BBB": [
            {"timestamp": 1_704_067_200, "block": 1, "share_price": 50},
            {"timestamp": 1_704_153_600, "block": 2, "share_price": 40},
        ],
    }
    prices = from_share_price_histories(histories)
    assert list(prices.columns) == ["AAA", "BBB"]
    rebased = normalized_prices(prices)
    assert rebased.iloc[0].tolist() == pytest.approx([1.0, 1.0])
    assert rebased.iloc[1, 0] == pytest.approx(1.1)


def test_multi_asset_covariance_and_per_column_ranking() -> None:
    """Covariance is finite, symmetric, labeled; ranking is univariate SASR."""
    rng = np.random.default_rng(2)
    idx = _daily_index(80)
    frame = pd.DataFrame(
        {
            "a": 0.001 + 0.01 * rng.normal(size=80),
            "b": 0.002 + 0.02 * rng.normal(size=80),
        },
        index=idx,
    )
    rs = ReturnSeries.from_returns(frame)
    cov = covariance.sample(rs)
    shrunk = covariance.ledoit_wolf(rs)
    assert list(cov.index) == ["a", "b"]
    assert list(cov.columns) == ["a", "b"]
    assert list(shrunk.columns) == ["a", "b"]
    assert np.isfinite(cov.to_numpy()).all()
    assert np.isfinite(shrunk.to_numpy()).all()
    assert cov.to_numpy() == pytest.approx(cov.to_numpy().T)
    assert shrunk.to_numpy() == pytest.approx(shrunk.to_numpy().T)
    ranking = rank_products(rs, RFR)
    assert list(ranking.index) == list(ranking.sort_values(ascending=False).index)
    per_col = ranking_metrics(rs, RFR)
    assert ranking["a"] == pytest.approx(per_col["a"].sasr)
    assert ranking["b"] == pytest.approx(per_col["b"].sasr)


def test_summary_sharpe_matches_sample_sharpe_not_sasr() -> None:
    """skfolio 365-day Sharpe matches Orion sample Sharpe and not SASR."""
    rng = np.random.default_rng(3)
    rs = _from_array(0.001 + 0.01 * rng.normal(size=30))
    table = measures.summary(rs, rfr=RFR)
    row = table.loc["a"]
    assert row["sharpe"] == pytest.approx(row["sample_sharpe"], rel=1e-10)
    assert row["sasr"] != pytest.approx(row["sharpe"])
    scoreboard = measures.product_scoreboard(rs, rfr=RFR)
    assert scoreboard.index[0] == "a"


def test_ranking_uses_compound_daily_rfr() -> None:
    """SASR excess uses the compounded daily rate, not rfr/365."""
    values = np.array([0.01, 0.02, -0.005, 0.003, 0.004] * 8)
    series = pd.Series(values, index=_daily_index(len(values)))
    metrics = rank_column(series, RFR)
    compound_daily = daily_rfr(RFR)
    mean_r = float(np.mean(values))
    sd = float(np.std(values, ddof=1))
    sr_compound = (mean_r - compound_daily) / sd
    sr_linear = (mean_r - RFR / 365) / sd
    assert metrics.sr_daily == pytest.approx(sr_compound)
    assert metrics.sr_daily != pytest.approx(sr_linear)


def test_pca_shapes_and_variance() -> None:
    """PCA loadings match the asset/component grid; variance ratios sum to 1."""
    rng = np.random.default_rng(4)
    idx = _daily_index(40)
    rs = ReturnSeries.from_returns(
        pd.DataFrame(
            {
                "a": rng.normal(scale=0.01, size=40),
                "b": rng.normal(scale=0.01, size=40),
                "c": rng.normal(scale=0.01, size=40),
            },
            index=idx,
        )
    )
    result = pca(rs)
    assert result.loadings.shape == (3, 3)
    assert result.scores.shape[0] == 40
    assert result.explained_variance_ratio.sum() == pytest.approx(1.0)


def test_min_variance_drops_flat_column_and_weights_sum() -> None:
    """MeanRisk min-variance drops zero-vol assets; remaining weights sum to 1."""
    rng = np.random.default_rng(5)
    idx = _daily_index(50)
    rs = ReturnSeries.from_returns(
        pd.DataFrame(
            {
                "risky": rng.normal(scale=0.01, size=50),
                "other": rng.normal(scale=0.02, size=50),
                "flat": np.zeros(50),
            },
            index=idx,
        )
    )
    fitted = min_variance(rs)
    assert "flat" in fitted.dropped
    assert "flat" not in fitted.weights.index
    assert np.isfinite(fitted.weights.to_numpy()).all()
    assert fitted.weights.sum() == pytest.approx(1.0)
    train, test = chronological_split(rs.returns[["risky", "other"]], test_size=0.3)
    assert len(train) + len(test) == 50
    assert train.index.max() < test.index.min()


def test_expanding_sasr_last_row_matches_rank_products() -> None:
    """Last expanding SASR equals rank_products; early |sasr| < |dasr|."""
    rng = np.random.default_rng(6)
    values = 0.02 + 0.005 * rng.normal(size=30)
    rs = _from_array(values)
    path = expanding_sasr(rs, RFR)
    latest = rank_products(rs, RFR)
    assert path.iloc[-1]["a"] == pytest.approx(latest["a"])
    prefix = rs.returns["a"].iloc[:10]
    early = rank_column(prefix, RFR)
    assert path.iloc[9]["a"] == pytest.approx(early.sasr)
    assert early.dasr is not None and early.sasr is not None
    assert abs(early.sasr) < abs(early.dasr)
