"""Tests for manager-facing execution cost dates."""

from datetime import datetime, timedelta, timezone

import pytest
from orion_finance_sdk_py.costs.dates import parse_cost_timestamp


def test_default_is_now_utc_date():
    before = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    label, unix = parse_cost_timestamp(None)
    after = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert label in {before, after}
    assert unix > 1_000_000_000


def test_calendar_date_is_end_of_utc_day():
    label, unix = parse_cost_timestamp("2026-08-01")
    assert label == "2026-08-01"
    end = (
        datetime(2026, 8, 1, tzinfo=timezone.utc)
        + timedelta(days=1)
        - timedelta(seconds=1)
    )
    assert unix == int(end.timestamp())


def test_rejects_unix_and_other_formats():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_cost_timestamp("1754092799")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_cost_timestamp("01/08/2026")
    with pytest.raises(TypeError):
        parse_cost_timestamp(1754092799)  # type: ignore[arg-type]


def test_rejects_future_utc_date():
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    with pytest.raises(ValueError, match="later than the current UTC date"):
        parse_cost_timestamp(future)
