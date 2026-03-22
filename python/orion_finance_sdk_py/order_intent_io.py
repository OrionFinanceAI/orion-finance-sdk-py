"""Load order intents from JSON, CSV, Parquet, inline strings, or dicts.

No third-party I/O helpers (e.g. readwrite): JSON/CSV use the stdlib; Parquet uses
optional ``pyarrow`` (``pip install 'orion-finance-sdk-py[parquet]'``).
"""

from __future__ import annotations

import ast
import csv
import json
import os
from pathlib import Path
from typing import Any

# Tabular: token column aliases (case-insensitive)
_ADDRESS_KEYS = frozenset({"address", "token", "addr"})
# Value columns: percentage_of_tvl is documented as 0–100
_PERCENT_KEYS = frozenset({"percentage_of_tvl", "percentage", "pct", "percent"})
_WEIGHT_KEYS = frozenset({"weight", "value", "allocation"})


def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _pick_tabular_columns(
    headers: list[str],
) -> tuple[str, str, str]:
    """Pick (raw_addr_header, raw_value_header, mode).

    mode is ``percent`` (0–100) or ``weight`` (infer fraction vs percent from data).
    """
    norm = {_normalize_header(h): h for h in headers}

    addr_h = None
    for key in _ADDRESS_KEYS:
        if key in norm:
            addr_h = norm[key]
            break

    if addr_h is None:
        raise ValueError(
            "CSV/Parquet must include an address column "
            f"(one of: {', '.join(sorted(_ADDRESS_KEYS))}). "
            f"Found columns: {headers!r}"
        )

    val_h = None
    mode = "weight"
    for key in _PERCENT_KEYS:
        if key in norm:
            val_h = norm[key]
            mode = "percent"
            break
    if val_h is None:
        for key in _WEIGHT_KEYS:
            if key in norm:
                val_h = norm[key]
                mode = "weight"
                break

    if val_h is None:
        raise ValueError(
            "CSV/Parquet must include a weight column "
            f"(one of: {', '.join(sorted(_PERCENT_KEYS | _WEIGHT_KEYS))}). "
            f"Found columns: {headers!r}"
        )

    return addr_h, val_h, mode


def _weights_from_percent_column(raw: dict[str, float]) -> dict[str, float]:
    return {k: float(v) / 100.0 for k, v in raw.items()}


def _weights_from_weight_column(raw: dict[str, float]) -> dict[str, float]:
    values = list(raw.values())
    if not values:
        raise ValueError("Order intent has no rows")
    s = sum(values)
    if s <= 0:
        raise ValueError("Sum of weights must be positive")
    # Documented table uses 0–100; if values look like fractions already, leave them
    if max(values) <= 1.0 + 1e-9 and abs(s - 1.0) <= 0.02:
        return {k: float(v) for k, v in raw.items()}
    if 99.0 <= s <= 101.0 or max(values) > 1.0:
        return {k: float(v) / 100.0 for k, v in raw.items()}
    raise ValueError(
        "Could not interpret weight column: values should sum to ~1 (fractions) "
        "or ~100 (percentages). "
        f"Got sum={s!r}, max={max(values)!r}"
    )


def _tabular_rows_to_dict(
    rows: list[dict[str, str]], headers: list[str]
) -> dict[str, float]:
    addr_h, val_h, mode = _pick_tabular_columns(headers)
    out: dict[str, float] = {}
    for row in rows:
        addr = (row.get(addr_h) or "").strip()
        if not addr:
            continue
        cell = (row.get(val_h) or "").strip()
        try:
            val = float(cell)
        except ValueError as e:
            raise ValueError(f"Invalid numeric weight for {addr!r}: {cell!r}") from e
        if addr in out:
            raise ValueError(f"Duplicate address in table: {addr!r}")
        out[addr] = val

    if mode == "percent":
        return _weights_from_percent_column(out)
    if mode == "weight":
        return _weights_from_weight_column(out)
    raise RuntimeError(f"unknown mode {mode!r}")


def _load_json_path(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_csv_path(path: Path) -> dict[str, float]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        headers = list(reader.fieldnames)
        rows = [dict(row) for row in reader]
    return _tabular_rows_to_dict(rows, headers)


def _load_parquet_path(path: Path) -> dict[str, float]:
    try:
        import pyarrow.parquet as pq
    except ImportError as e:
        raise ImportError(
            "Reading Parquet requires pyarrow. Install with: "
            "pip install 'orion-finance-sdk-py[parquet]'"
        ) from e

    table = pq.read_table(path)
    names = table.column_names
    headers = list(names)
    rows: list[dict[str, str]] = []
    n = table.num_rows
    for i in range(n):
        row: dict[str, str] = {}
        for name in names:
            col = table.column(name)
            v = col[i].as_py()
            if v is None:
                row[name] = ""
            else:
                row[name] = str(v)
        rows.append(row)
    return _tabular_rows_to_dict(rows, headers)


def _coerce_mapping(data: Any) -> dict[str, float]:
    if isinstance(data, list):
        # List of {address, percentage_of_tvl} objects
        if not data:
            raise ValueError("Order intent list is empty")
        if isinstance(data[0], dict):
            rows = []
            headers: set[str] = set()
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError(
                        "List items must be objects with address/weight fields"
                    )
                rows.append({str(k): str(v) for k, v in item.items()})
                headers.update(item.keys())
            return _tabular_rows_to_dict(rows, sorted(headers))
        raise ValueError("Unsupported JSON list format for order intent")

    if not isinstance(data, dict):
        raise ValueError(
            f"Order intent must be a JSON object mapping addresses to weights, "
            f"got {type(data).__name__}"
        )

    # Strict: all keys str-like, all values numeric
    out: dict[str, float] = {}
    for k, v in data.items():
        key = str(k).strip()
        if not key:
            continue
        try:
            out[key] = float(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Non-numeric weight for {key!r}: {v!r}") from e
    if not out:
        raise ValueError("Order intent object is empty")
    return out


def _load_path(path: Path) -> dict[str, float]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = _load_json_path(path)
        return _coerce_mapping(data)
    if suffix == ".csv":
        return _load_csv_path(path)
    if suffix in (".parquet", ".pq"):
        return _load_parquet_path(path)
    raise ValueError(
        f"Unsupported file type {suffix!r} for order intent "
        "(supported: .json, .csv, .parquet, .pq)"
    )


def _parse_inline_object(text: str) -> dict[str, float]:
    t = text.strip()
    if not t:
        raise ValueError("Order intent string is empty")
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(t)
        except (ValueError, SyntaxError) as e:
            raise ValueError(
                "Could not parse order intent as JSON object or Python literal dict"
            ) from e
    return _coerce_mapping(data)


def _looks_like_inline_dict(text: str) -> bool:
    t = _strip_bom(text.strip())
    return bool(t) and t[0] in "{["


def load_order_intent(
    source: str | dict[str, Any] | os.PathLike[str],
) -> dict[str, float]:
    """Load an order intent as ``address -> weight`` fractions (summing to ~1).

    * **dict** — must map token address strings to numeric weights (same as JSON object).
    * **path** — existing file: ``.json`` (object), ``.csv`` / ``.parquet`` (tabular),
      see docs for column names.
    * **str** — if it is not an existing file path, parsed as inline JSON object or
      Python ``dict`` literal (e.g. ``'{"0x...": 0.5, ...}'``).

    Args:
        source: File path, inline JSON/dict string, or mapping.

    Returns:
        Mapping of checksummable address strings to float weights (before
        :func:`validate_order` scaling).

    Raises:
        ValueError: Invalid shape, missing columns, or parse error.
        ImportError: Parquet requested without ``pyarrow`` installed.
    """
    if isinstance(source, dict):
        return _coerce_mapping(source)

    if isinstance(source, (str, os.PathLike)):
        raw = os.fspath(source)
        raw = _strip_bom(raw.strip())
        if not raw:
            raise ValueError("Order intent source is empty")

        expanded = os.path.expanduser(raw)
        p = Path(expanded)
        if p.is_file():
            return _load_path(p.resolve())

        if _looks_like_inline_dict(raw):
            return _parse_inline_object(raw)

        raise ValueError(
            f"Order intent is not an existing file and not a JSON object string: {raw!r}"
        )

    raise TypeError(f"Unsupported order intent source type: {type(source).__name__}")
