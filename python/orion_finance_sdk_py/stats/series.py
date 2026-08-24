"""Datetime-indexed simple-return panels with Orion ranking hygiene."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from orion_finance_sdk_py.stats._frame import (
    as_dataframe,
    mask_gap_boundary_returns,
    mask_nonpositive_prices,
    require_datetime_index,
)
from orion_finance_sdk_py.stats.constants import DEFAULT_PERIODS_PER_YEAR
from orion_finance_sdk_py.stats.rfr import excess_returns as subtract_rfr


class ReturnSeries:
    """Simple-return panel with contiguous-daily ranking hygiene.

    ``returns`` is the contiguous one-calendar-day panel used for SASR, sample
    Sharpe, covariance, PCA, and MeanRisk. Path statistics use ``prices`` when
    the object was built from a price panel (gaps included).
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        *,
        prices: pd.DataFrame | None = None,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> None:
        """Store already-hygiened contiguous daily returns and optional prices."""
        if periods_per_year <= 0:
            raise ValueError("periods_per_year must be positive")
        self._returns = returns
        self._prices = prices
        self.periods_per_year = periods_per_year

    @classmethod
    def from_returns(
        cls,
        returns: pd.Series | pd.DataFrame,
        *,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> ReturnSeries:
        """Build from a DatetimeIndex panel of simple returns."""
        frame = as_dataframe(returns)
        require_datetime_index(frame)
        contiguous = mask_gap_boundary_returns(frame.astype(float))
        return cls(contiguous, prices=None, periods_per_year=periods_per_year)

    @classmethod
    def from_prices(
        cls,
        prices: pd.Series | pd.DataFrame,
        *,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> ReturnSeries:
        """Build from a DatetimeIndex panel of strictly positive prices."""
        price_frame = mask_nonpositive_prices(as_dataframe(prices).astype(float))
        require_datetime_index(price_frame)
        simple = price_frame.pct_change(fill_method=None)
        contiguous = mask_gap_boundary_returns(simple)
        return cls(contiguous, prices=price_frame, periods_per_year=periods_per_year)

    @classmethod
    def from_price_history(
        cls,
        series: Sequence[Mapping[str, Any]],
        *,
        decimals: int,
        names: Mapping[str, str] | None = None,
        min_obs: int | None = None,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> ReturnSeries:
        """Build from ``PriceAdapterRegistry.price_history`` records."""
        from orion_finance_sdk_py.stats.panels import from_price_history

        prices = from_price_history(
            series, decimals=decimals, names=names, min_obs=min_obs
        )
        return cls.from_prices(prices, periods_per_year=periods_per_year)

    @classmethod
    def from_share_price_histories(
        cls,
        histories: Mapping[str, Iterable[Mapping[str, Any]]],
        *,
        min_obs: int | None = None,
        periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    ) -> ReturnSeries:
        """Build from vault ``share_price_history`` records keyed by symbol."""
        from orion_finance_sdk_py.stats.panels import from_share_price_histories

        prices = from_share_price_histories(histories, min_obs=min_obs)
        return cls.from_prices(prices, periods_per_year=periods_per_year)

    @property
    def returns(self) -> pd.DataFrame:
        """Daily simple-return panel with gap-boundary rows set to NaN."""
        return self._returns

    @property
    def prices(self) -> pd.DataFrame | None:
        """Source prices when built from a price panel; otherwise ``None``."""
        return self._prices

    @property
    def columns(self) -> pd.Index:
        """Asset labels."""
        return self._returns.columns

    def excess_returns(self, rfr: float) -> pd.DataFrame:
        """Contiguous daily simple returns minus the compounded per-period RFR."""
        return subtract_rfr(
            self._returns,
            rfr,
            periods_per_year=self.periods_per_year,
        )
