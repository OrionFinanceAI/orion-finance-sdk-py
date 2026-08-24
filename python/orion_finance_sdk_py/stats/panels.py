"""Build labeled price panels from on-chain history dicts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd


def _asset_label(addr: str, names: Mapping[str, str] | None) -> str:
    """Prefer a whitelist name; otherwise a shortened address."""
    if names:
        for key in (addr, addr.lower()):
            if key in names:
                return str(names[key])
    if len(addr) >= 10:
        return f"{addr[:6]}...{addr[-4:]}"
    return addr


def _to_utc_index(index: pd.Index) -> pd.DatetimeIndex:
    """Interpret unix-second labels as UTC timestamps."""
    return pd.to_datetime(index, unit="s", utc=True)


def from_price_history(
    series: Sequence[Mapping[str, Any]],
    *,
    decimals: int,
    names: Mapping[str, str] | None = None,
    min_obs: int | None = None,
) -> pd.DataFrame:
    """Turn ``PriceAdapterRegistry.price_history`` dicts into a price panel.

    Args:
        series: List of ``{"timestamp", "block", "prices"}`` records.
        decimals: ``price_adapter_decimals`` used to scale integer prices.
        names: Optional address → display name map.
        min_obs: Drop columns with fewer than this many non-null observations.
    """
    if decimals < 0:
        raise ValueError("decimals must be non-negative")
    scale = 10**decimals
    rows: list[dict[str, Any]] = []
    for point in series:
        row: dict[str, Any] = {"timestamp": point["timestamp"]}
        prices = point.get("prices") or {}
        for addr, px in prices.items():
            row[_asset_label(str(addr), names)] = float(px) / scale
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    frame = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["timestamp"], keep="last")
        .set_index("timestamp")
        .sort_index()
    )
    frame.index = _to_utc_index(frame.index)
    frame = frame.astype(float)
    if min_obs is not None:
        frame = frame.dropna(axis=1, thresh=min_obs)
    return frame


def from_share_price_histories(
    histories: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    min_obs: int | None = None,
) -> pd.DataFrame:
    """Turn vault ``share_price_history`` dicts into a labeled price panel.

    Args:
        histories: Map of column name → list of
            ``{"timestamp", "block", "share_price"}`` records.
        min_obs: Drop columns with fewer than this many non-null observations.
    """
    frames: list[pd.DataFrame] = []
    for name, points in histories.items():
        rows = [
            {"timestamp": point["timestamp"], name: point["share_price"]}
            for point in points
        ]
        if not rows:
            continue
        frame = (
            pd.DataFrame(rows)
            .drop_duplicates(subset=["timestamp"], keep="last")
            .set_index("timestamp")
        )
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    prices = pd.concat(frames, axis=1).sort_index()
    prices.index = _to_utc_index(prices.index)
    prices = prices.astype(float)
    if min_obs is not None:
        prices = prices.dropna(axis=1, thresh=min_obs)
    return prices


def normalized_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Rebase each column to 1.0 at its first valid observation."""
    out = prices.copy()
    for col in out.columns:
        valid = out[col].dropna()
        if valid.empty:
            continue
        out[col] = out[col] / float(valid.iloc[0])
    return out
