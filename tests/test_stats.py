"""Tests for return-series hygiene, SASR ranking, and skfolio wrappers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from orion_finance_sdk_py import ReturnSeries, covariance, measures, rank_products
from orion_finance_sdk_py.stats._frame import as_dataframe, gap_boundary_mask
from orion_finance_sdk_py.stats.constants import TRACK_RECORD_FULL_TRUST_WEEKS
from orion_finance_sdk_py.stats.factors import pca
from orion_finance_sdk_py.stats.panels import (
    _asset_label,
    from_price_history,
    from_share_price_histories,
    normalized_prices,
)
from orion_finance_sdk_py.stats.portfolio import (
    chronological_split,
    max_sharpe,
    max_sortino,
    min_variance,
)
from orion_finance_sdk_py.stats.ranking import (
    expanding_sasr,
    rank_column,
    ranking_metrics,
)
from orion_finance_sdk_py.stats.rfr import daily_rfr, excess_returns, rfr_decimal

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
    expected_w = min(1.0, max(0.0, (metrics.t_eff / 7.0) / TRACK_RECORD_FULL_TRUST_WEEKS))
    assert metrics.w == pytest.approx(expected_w)
    assert metrics.w < 1.0
    assert metrics.sasr == pytest.approx(metrics.dasr * metrics.w)
    assert metrics.sasr < metrics.dasr


def test_negative_lag1_keeps_teff_and_w_nonnegative() -> None:
    """Strong mean-reversion (ρ ≤ -0.5) must not yield negative T_eff or w."""
    values = np.tile([0.02, -0.01], 20)
    metrics = rank_column(pd.Series(values, index=_daily_index(len(values))), RFR)
    assert metrics.rho is not None and metrics.rho < -0.4
    assert metrics.t_eff is not None and metrics.t_eff > 0.0
    assert metrics.w is not None and 0.0 <= metrics.w <= 1.0


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


def test_summary_with_prices_fills_path_stats() -> None:
    """from_prices path fills total_return, cagr, max_drawdown, total_excess."""
    idx = _daily_index(10)
    prices = pd.Series(
        [100.0, 102.0, 101.0, 105.0, 104.0, 108.0, 110.0, 109.0, 112.0, 115.0],
        index=idx,
        name="a",
    )
    rs = ReturnSeries.from_prices(prices)
    table = measures.summary(rs, rfr=RFR)
    row = table.loc["a"]
    assert row["total_return"] == pytest.approx(115.0 / 100.0 - 1.0)
    assert np.isfinite(row["cagr"])
    assert np.isfinite(row["max_drawdown"])
    assert np.isfinite(row["total_excess"])
    assert row["total_excess"] < row["total_return"]


def test_summary_empty_column_is_nan_row() -> None:
    """All-NaN returns yield n_obs == 0 and NaN measure columns."""
    idx = _daily_index(3)
    rs = ReturnSeries.from_returns(
        pd.Series([np.nan, np.nan, np.nan], index=idx, name="empty")
    )
    table = measures.summary(rs, rfr=RFR)
    row = table.loc["empty"]
    assert row["n_obs"] == 0
    for col in ("mean", "vol", "sharpe", "sortino", "cvar", "var", "max_drawdown"):
        assert np.isnan(row[col])


def test_summary_zero_vol_sharpe_and_sortino_nan() -> None:
    """When sample and semi std are zero, sharpe and sortino are NaN."""
    from unittest.mock import patch

    values = 0.001 + 0.01 * np.random.default_rng(12).normal(size=20)
    rs = _from_array(values)
    with (
        patch(
            "orion_finance_sdk_py.stats.measures.standard_deviation", return_value=0.0
        ),
        patch("orion_finance_sdk_py.stats.measures.semi_deviation", return_value=0.0),
    ):
        table = measures.summary(rs, rfr=RFR)
    row = table.loc["a"]
    assert row["n_obs"] == 20
    assert np.isnan(row["sharpe"])
    assert np.isnan(row["sortino"])


def test_summary_path_helper_edge_nans() -> None:
    """Path helpers return NaN for short / invalid price paths."""
    from orion_finance_sdk_py.stats import measures as measures_mod

    short = pd.Series([100.0], index=_daily_index(1))
    assert np.isnan(measures_mod._path_total_return(short))
    assert np.isnan(measures_mod._cagr(short, 365))
    assert np.isnan(measures_mod._path_max_drawdown(short))
    assert np.isnan(measures_mod._period_max_drawdown(np.array([0.01])))

    zero_first = pd.Series([0.0, 110.0], index=_daily_index(2))
    assert np.isnan(measures_mod._path_total_return(zero_first))

    same_day = pd.Series(
        [100.0, 110.0],
        index=pd.DatetimeIndex(["2024-01-01T00:00:00Z", "2024-01-01T12:00:00Z"]),
    )
    assert np.isnan(measures_mod._cagr(same_day, 365))

    crossed_zero = pd.Series([100.0, -50.0], index=_daily_index(2))
    assert np.isnan(measures_mod._cagr(crossed_zero, 365))


def test_max_sharpe_and_max_sortino_weights_sum() -> None:
    """max_sharpe / max_sortino return finite weights that sum to 1."""
    rng = np.random.default_rng(8)
    idx = _daily_index(60)
    rs = ReturnSeries.from_returns(
        pd.DataFrame(
            {
                "a": 0.001 + 0.01 * rng.normal(size=60),
                "b": 0.002 + 0.015 * rng.normal(size=60),
                "c": 0.0005 + 0.012 * rng.normal(size=60),
            },
            index=idx,
        )
    )
    for fitted in (max_sharpe(rs, rfr=RFR), max_sortino(rs, rfr=RFR)):
        assert np.isfinite(fitted.weights.to_numpy()).all()
        assert fitted.weights.sum() == pytest.approx(1.0)
        assert isinstance(fitted.dropped, tuple)


def test_fitted_portfolio_predict_keeps_weight_columns() -> None:
    """predict runs on OOS returns restricted to fitted weight columns."""
    rng = np.random.default_rng(9)
    idx = _daily_index(40)
    frame = pd.DataFrame(
        {
            "a": rng.normal(scale=0.01, size=40),
            "b": rng.normal(scale=0.02, size=40),
        },
        index=idx,
    )
    rs = ReturnSeries.from_returns(frame)
    fitted = min_variance(rs)
    train, test = chronological_split(rs, test_size=0.25)
    portfolio = fitted.predict(test)
    assert portfolio is not None


def test_chronological_split_rejects_bad_test_size() -> None:
    """test_size outside (0, 1) or emptying a side raises ValueError."""
    idx = _daily_index(10)
    frame = pd.DataFrame({"a": np.linspace(0.01, 0.02, 10)}, index=idx)
    with pytest.raises(ValueError, match="test_size"):
        chronological_split(frame, test_size=0.0)
    with pytest.raises(ValueError, match="test_size"):
        chronological_split(frame, test_size=1.0)
    tiny = pd.DataFrame({"a": [0.01]}, index=_daily_index(1))
    with pytest.raises(ValueError, match="empty"):
        chronological_split(tiny, test_size=0.5)


def test_min_variance_rejects_single_asset() -> None:
    """After dropping flat columns, fewer than 2 assets raises ValueError."""
    rng = np.random.default_rng(10)
    idx = _daily_index(30)
    rs = ReturnSeries.from_returns(
        pd.DataFrame(
            {
                "risky": rng.normal(scale=0.01, size=30),
                "flat": np.zeros(30),
            },
            index=idx,
        )
    )
    with pytest.raises(ValueError, match="MeanRisk needs at least 2"):
        min_variance(rs)


def test_asset_label_shortens_address_without_names() -> None:
    """Long addresses shorten in lowercase; short labels pass through unchanged."""
    long_addr = "0xabcDEF0000000000000000000000000000000001"
    assert _asset_label(long_addr, None) == "0xabcd...0001"
    assert _asset_label("USDC", None) == "USDC"


def test_from_price_history_errors_and_min_obs() -> None:
    """decimals < 0 errors; empty series → empty frame; min_obs drops sparse cols."""
    with pytest.raises(ValueError, match="decimals"):
        from_price_history([], decimals=-1)
    assert from_price_history([], decimals=8).empty
    series = [
        {
            "timestamp": 1_704_067_200,
            "block": 1,
            "prices": {
                "0xaaa0000000000000000000000000000000000001": 10**8,
                "0xbbb0000000000000000000000000000000000002": 10**8,
            },
        },
        {
            "timestamp": 1_704_153_600,
            "block": 2,
            "prices": {"0xaaa0000000000000000000000000000000000001": 2 * 10**8},
        },
    ]
    prices = from_price_history(series, decimals=8, min_obs=2)
    assert list(prices.columns) == ["0xaaa0...0001"]


def test_from_share_price_histories_empty_and_min_obs() -> None:
    """Empty histories skip; min_obs drops sparse vault columns."""
    assert from_share_price_histories({}).empty
    assert from_share_price_histories({"A": []}).empty
    histories = {
        "AAA": [
            {"timestamp": 1_704_067_200, "block": 1, "share_price": 100},
            {"timestamp": 1_704_153_600, "block": 2, "share_price": 110},
        ],
        "BBB": [
            {"timestamp": 1_704_067_200, "block": 1, "share_price": 50},
        ],
        "CCC": [],
    }
    prices = from_share_price_histories(histories, min_obs=2)
    assert list(prices.columns) == ["AAA"]


def test_normalized_prices_skips_all_nan_column() -> None:
    """All-NaN and non-positive first-price columns are left untouched."""
    idx = _daily_index(3)
    prices = pd.DataFrame(
        {
            "ok": [100.0, 110.0, 120.0],
            "bad": [np.nan, np.nan, np.nan],
            "zero": [0.0, 10.0, 20.0],
            "neg": [-5.0, 10.0, 20.0],
        },
        index=idx,
    )
    rebased = normalized_prices(prices)
    assert rebased["ok"].iloc[0] == pytest.approx(1.0)
    assert rebased["bad"].isna().all()
    assert rebased["zero"].tolist() == pytest.approx([0.0, 10.0, 20.0])
    assert rebased["neg"].tolist() == pytest.approx([-5.0, 10.0, 20.0])


def test_return_series_from_share_price_histories() -> None:
    """ReturnSeries.from_share_price_histories builds priced returns."""
    histories = {
        "AAA": [
            {"timestamp": 1_704_067_200, "block": 1, "share_price": 100},
            {"timestamp": 1_704_153_600, "block": 2, "share_price": 110},
        ],
    }
    rs = ReturnSeries.from_share_price_histories(histories)
    assert rs.prices is not None
    assert "AAA" in rs.columns
    assert rs.returns["AAA"].iloc[1] == pytest.approx(0.1)


def test_return_series_excess_returns_matches_daily_rfr() -> None:
    """excess_returns subtracts the compounded daily RFR."""
    values = np.array([0.01, 0.02, -0.005])
    rs = _from_array(values)
    excess = rs.excess_returns(RFR)
    expected = values - daily_rfr(RFR)
    assert excess["a"].to_numpy() == pytest.approx(expected)


def test_return_series_rejects_nonpositive_periods() -> None:
    """periods_per_year <= 0 raises ValueError."""
    with pytest.raises(ValueError, match="periods_per_year"):
        ReturnSeries(
            pd.DataFrame({"a": [0.01]}, index=_daily_index(1)), periods_per_year=0
        )


def test_covariance_correlation_labeled_and_symmetric() -> None:
    """correlation is labeled, finite, and symmetric."""
    rng = np.random.default_rng(11)
    idx = _daily_index(50)
    rs = ReturnSeries.from_returns(
        pd.DataFrame(
            {
                "a": rng.normal(scale=0.01, size=50),
                "b": rng.normal(scale=0.02, size=50),
            },
            index=idx,
        )
    )
    corr = covariance.correlation(rs)
    assert list(corr.columns) == ["a", "b"]
    assert np.isfinite(corr.to_numpy()).all()
    assert corr.to_numpy() == pytest.approx(corr.to_numpy().T)


def test_overlapping_returns_empty_raises() -> None:
    """No overlapping contiguous returns raises ValueError."""
    idx = _daily_index(3)
    frame = pd.DataFrame(
        {"a": [0.01, np.nan, 0.02], "b": [np.nan, 0.01, np.nan]},
        index=idx,
    )
    with pytest.raises(ValueError, match="overlapping"):
        covariance.sample(frame)


def test_daily_rfr_rejects_nonpositive_periods() -> None:
    """daily_rfr rejects non-positive periods_per_year."""
    with pytest.raises(ValueError, match="periods_per_year"):
        daily_rfr(RFR, periods_per_year=0)


def test_excess_returns_accepts_series() -> None:
    """Module excess_returns accepts a Series and returns a DataFrame."""
    series = pd.Series([0.01, 0.02], index=_daily_index(2), name="a")
    out = excess_returns(series, RFR)
    assert isinstance(out, pd.DataFrame)
    assert out["a"].iloc[0] == pytest.approx(0.01 - daily_rfr(RFR))


def test_as_dataframe_and_datetime_index_type_errors() -> None:
    """as_dataframe and gap_boundary_mask reject bad inputs / empty index."""
    with pytest.raises(TypeError, match="Series or DataFrame"):
        as_dataframe([1, 2, 3])  # type: ignore[arg-type]
    frame = pd.DataFrame({"a": [0.01, 0.02]})
    with pytest.raises(TypeError, match="DatetimeIndex"):
        ReturnSeries.from_returns(frame)
    empty = gap_boundary_mask(pd.DatetimeIndex([]))
    assert len(empty) == 0
    assert empty.dtype == bool


def test_from_returns_rejects_unsorted_index() -> None:
    """Unsorted DatetimeIndex is rejected so gap masking stays well-defined."""
    idx = pd.to_datetime(
        ["2024-01-03", "2024-01-01", "2024-01-02"],
        utc=True,
    )
    frame = pd.DataFrame({"a": [0.01, 0.02, 0.03]}, index=idx)
    with pytest.raises(ValueError, match="monotonically increasing"):
        ReturnSeries.from_returns(frame)
