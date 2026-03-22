"""Tests for order_intent_io."""

import json
from unittest.mock import patch

import pytest
from orion_finance_sdk_py import order_intent_io as oio
from orion_finance_sdk_py.order_intent_io import load_order_intent


def test_load_dict():
    assert load_order_intent({"0xA": 0.5, "0xB": 0.5}) == {"0xA": 0.5, "0xB": 0.5}


def test_load_json_file(tmp_path):
    p = tmp_path / "o.json"
    p.write_text(json.dumps({"0xA": 1.0}), encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_path_pathlike(tmp_path):
    p = tmp_path / "o.json"
    p.write_text(json.dumps({"0xA": 1.0}), encoding="utf-8")
    assert load_order_intent(p) == {"0xA": 1.0}


def test_load_inline_json():
    assert load_order_intent('{"0xA": 0.25, "0xB": 0.75}') == {
        "0xA": 0.25,
        "0xB": 0.75,
    }


def test_load_inline_python_literal():
    assert load_order_intent("{'0xA': 0.4, '0xB': 0.6}") == {"0xA": 0.4, "0xB": 0.6}


def test_strip_bom_inline():
    assert load_order_intent('\ufeff{"0xA": 1.0}') == {"0xA": 1.0}


def test_expanduser_tilde_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    f = tmp_path / "o.json"
    f.write_text('{"0xC": 1.0}', encoding="utf-8")
    assert load_order_intent("~/o.json") == {"0xC": 1.0}


def test_empty_source_string():
    with pytest.raises(ValueError, match="empty"):
        load_order_intent("   ")


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


def test_load_csv_token_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("token,weight\n0xA,1.0\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_csv_addr_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("addr,weight\n0xA,1.0\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_csv_header_spaces_normalize_to_address(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text(" Address , weight \n0xA,1.0\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_csv_pct_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,pct\n0xA,50\n0xB,50\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 0.5, "0xB": 0.5}


def test_load_csv_percent_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,percent\n0xA,100\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_csv_value_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,value\n0xA,50\n0xB,50\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 0.5, "0xB": 0.5}


def test_load_csv_allocation_alias(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,allocation\n0xA,1.0\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_load_csv_skip_blank_address_row(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n,0.5\n0xB,1.0\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xB": 1.0}


def test_load_csv_all_rows_blank_address_weight_mode(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no rows"):
        load_order_intent(str(p))


def test_load_csv_weight_sum_not_positive(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n0xA,-1\n0xB,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Sum of weights must be positive"):
        load_order_intent(str(p))


def test_load_csv_weight_sum_near_100(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n0xA,50\n0xB,50\n", encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 0.5, "0xB": 0.5}


def test_load_csv_no_address_column(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="address column"):
        load_order_intent(str(p))


def test_load_csv_no_weight_column(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address\n0xA\n", encoding="utf-8")
    with pytest.raises(ValueError, match="weight column"):
        load_order_intent(str(p))


def test_load_csv_invalid_numeric_cell(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n0xA,not-a-number\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid numeric weight"):
        load_order_intent(str(p))


def test_load_csv_duplicate_address(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n0xA,0.5\n0xA,0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate address"):
        load_order_intent(str(p))


def test_load_csv_ambiguous_weight_sum(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("address,weight\n0xA,0.3\n0xB,0.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not interpret weight column"):
        load_order_intent(str(p))


def test_load_csv_no_header_row(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no header"):
        load_order_intent(str(p))


def test_not_file_not_json_raises():
    with pytest.raises(ValueError, match="not an existing file"):
        load_order_intent("definitely-not-a-file-xyz123.json")


def test_parse_inline_garbage():
    with pytest.raises(ValueError, match="Could not parse"):
        load_order_intent("{not valid json")


def test_parse_inline_object_empty():
    with pytest.raises(ValueError, match="empty"):
        oio._parse_inline_object("   ")


def test_unsupported_file_suffix(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("foo", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_order_intent(str(p))


def test_json_file_list_rows(tmp_path):
    p = tmp_path / "o.json"
    rows = [
        {"address": "0xA", "percentage_of_tvl": 25},
        {"address": "0xB", "percentage_of_tvl": 75},
    ]
    p.write_text(json.dumps(rows), encoding="utf-8")
    assert load_order_intent(str(p)) == {"0xA": 0.25, "0xB": 0.75}


def test_json_file_top_level_int(tmp_path):
    p = tmp_path / "o.json"
    p.write_text("42", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object mapping"):
        load_order_intent(str(p))


def test_coerce_empty_list():
    with pytest.raises(ValueError, match="list is empty"):
        oio._coerce_mapping([])


def test_coerce_list_non_dict_items():
    with pytest.raises(ValueError, match="Unsupported JSON list format"):
        oio._coerce_mapping([1, 2])


def test_coerce_list_item_not_dict():
    with pytest.raises(ValueError, match="List items must be objects"):
        oio._coerce_mapping([{"address": "0xA", "weight": 1}, "x"])


def test_coerce_empty_dict():
    with pytest.raises(ValueError, match="empty"):
        load_order_intent({})


def test_coerce_blank_keys_skipped():
    assert load_order_intent({"0xA": 1.0, "": 0.0}) == {"0xA": 1.0}


def test_coerce_non_numeric_weight():
    with pytest.raises(ValueError, match="Non-numeric weight"):
        load_order_intent({"0xA": "nope"})


def test_type_error_unsupported_source_type():
    with pytest.raises(TypeError, match="Unsupported"):
        load_order_intent(123)  # type: ignore[arg-type]


def test_strip_bom_noop():
    assert oio._strip_bom("abc") == "abc"


def test_looks_like_inline_list():
    assert oio._looks_like_inline_dict("[1]") is True


def test_runtime_unknown_mode_via_mock():
    with patch.object(oio, "_pick_tabular_columns", return_value=("a", "w", "bogus")):
        with pytest.raises(RuntimeError, match="unknown mode"):
            oio._tabular_rows_to_dict(
                [{"a": "0x1", "w": "1.0"}],
                ["a", "w"],
            )


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


def test_parquet_pq_suffix(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    p = tmp_path / "o.pq"
    table = pa.table({"address": ["0xA"], "weight": [1.0]})
    pq.write_table(table, p)
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_parquet_null_cell_skipped(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    p = tmp_path / "o.parquet"
    table = pa.table(
        {
            "address": ["0xA", None],
            "percentage_of_tvl": [100.0, 0.0],
        }
    )
    pq.write_table(table, p)
    assert load_order_intent(str(p)) == {"0xA": 1.0}


def test_parquet_import_error(tmp_path):
    p = tmp_path / "x.parquet"
    p.write_bytes(b"dummy")

    real_import = __import__

    def fake_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "pyarrow.parquet" or (
            fromlist and "parquet" in fromlist and name == "pyarrow"
        ):
            raise ImportError("no pyarrow")
        return real_import(name, globals_, locals_, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="pyarrow"):
            oio._load_parquet_path(p)
