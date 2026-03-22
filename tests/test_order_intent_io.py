"""Tests for order_intent_io."""

import json

import pytest
from orion_finance_sdk_py.order_intent_io import load_order_intent


def test_load_dict():
    assert load_order_intent({"0xA": 0.5, "0xB": 0.5}) == {"0xA": 0.5, "0xB": 0.5}


def test_load_json_file(tmp_path):
    p = tmp_path / "o.json"
    p.write_text(json.dumps({"0xA": 1.0}), encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_inline_json():
    assert load_order_intent('{"0xA": 0.25, "0xB": 0.75}') == {
        "0xA": 0.25,
        "0xB": 0.75,
    }


def test_load_inline_python_literal():
    assert load_order_intent("{'0xA': 0.4, '0xB': 0.6}") == {"0xA": 0.4, "0xB": 0.6}


def test_load_csv_percentage(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text(
        "address,percentage_of_tvl\n0xA,40\n0xB,60\n",
        encoding="utf-8",
    )
    assert load_order_intent(str(p)) == {"0xA": 0.4, "0xB": 0.6}


def test_load_csv_weights_fractions(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text(
        "address,weight\n0xA,0.2\n0xB,0.8\n",
        encoding="utf-8",
    )
    assert load_order_intent(str(p)) == {"0xA": 0.2, "0xB": 0.8}


def test_not_file_not_json_raises():
    with pytest.raises(ValueError, match="not an existing file"):
        load_order_intent("definitely-not-a-file-xyz123.json")


def test_parquet_roundtrip(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    p = tmp_path / "o.parquet"
    table = pa.table(
        {
            "address": ["0xA", "0xB"],
            "percentage_of_tvl": [30.0, 70.0],
        }
    )
    pq.write_table(table, p)
    assert load_order_intent(str(p)) == {"0xA": 0.3, "0xB": 0.7}
