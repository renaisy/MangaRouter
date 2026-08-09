"""nocodb-init 表结构初始化的单元测试。

重点测纯逻辑：dt 类型映射、payload 构造、幂等查重的响应解析。
不真实调用 NocoDB（网络部分用 mock）。
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# 让测试能 import 上层的 init_schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import init_schema


# --------------------------------------------------------------------------- #
# resolve_dt：uidt → MySQL 类型映射（B1 核心）
# --------------------------------------------------------------------------- #
def test_resolve_dt_number_maps_to_int():
    assert init_schema.resolve_dt({"uidt": "Number"}) == "int"


def test_resolve_dt_date_maps_to_date():
    assert init_schema.resolve_dt({"uidt": "Date"}) == "date"


def test_resolve_dt_datetime_maps_to_timestamp():
    assert init_schema.resolve_dt({"uidt": "DateTime"}) == "timestamp"


def test_resolve_dt_text_types_map_to_varchar_or_text():
    assert init_schema.resolve_dt({"uidt": "SingleLineText"}) == "varchar"
    assert init_schema.resolve_dt({"uidt": "SingleSelect"}) == "varchar"
    assert init_schema.resolve_dt({"uidt": "LongText"}) == "text"


def test_resolve_dt_explicit_dt_overrides_mapping():
    """字段显式给 dt（如金额用 decimal）应优先于 uidt 映射。"""
    col = {"uidt": "Number", "dt": "decimal"}
    assert init_schema.resolve_dt(col) == "decimal"


def test_resolve_dt_unknown_uidt_falls_back_to_varchar():
    assert init_schema.resolve_dt({"uidt": "SomeNewType"}) == "varchar"


def test_amount_cost_budget_fields_are_decimal():
    """金额字段（Amount/Cost/Budget）必须是 decimal，否则 int 会丢小数。"""
    all_cols = {}
    for _, cols in init_schema.ALL_TABLES:
        for c in cols:
            all_cols[c["column_name"]] = c
    for money_field in ("Amount", "Cost", "Budget"):
        assert all_cols[money_field].get("dt") == "decimal", (
            f"{money_field} 必须显式标 dt=decimal，否则 uidt=Number 会映射成 int 丢失小数"
        )


# --------------------------------------------------------------------------- #
# build_columns_payload：建表 payload 构造（B1+B4）
# --------------------------------------------------------------------------- #
def test_build_columns_payload_includes_dt_for_each():
    cols = [
        {"column_name": "Cnt", "uidt": "Number"},
        {"column_name": "Day", "uidt": "Date"},
        {"title": "名", "column_name": "Name", "uidt": "SingleLineText", "rqd": True},
    ]
    payload = init_schema.build_columns_payload(cols)
    assert payload[0]["dt"] == "int"
    assert payload[1]["dt"] == "date"
    assert payload[2]["dt"] == "varchar"
    assert payload[2]["title"] == "名"
    assert payload[2]["rqd"] is True


def test_build_columns_payload_select_options_passed_through():
    cols = [{"column_name": "S", "uidt": "SingleSelect", "dtxp": "a,b,c", "dtxs": "a"}]
    payload = init_schema.build_columns_payload(cols)
    assert payload[0]["dtxp"] == "a,b,c"
    assert payload[0]["dtxs"] == "a"


def test_all_real_tables_build_payload_without_error():
    """四张真实表的列定义都能正确构造 payload（防字段定义笔误）。"""
    for title, cols in init_schema.ALL_TABLES:
        payload = init_schema.build_columns_payload(cols)
        assert len(payload) == len(cols)
        # 每列都必须有 dt（不能是空）
        for item in payload:
            assert item["dt"], f"{title}.{item['column_name']} 缺 dt"


# --------------------------------------------------------------------------- #
# create_table：返回值校验（B4）
# --------------------------------------------------------------------------- #
def test_create_table_raises_when_no_table_id():
    """拿不到 tableId 应抛异常而非返回空串（B4 修复）。"""
    with patch("init_schema.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"unexpected": "no id field"}
        mock_post.return_value = mock_resp
        with pytest.raises(RuntimeError, match="未返回 tableId"):
            init_schema.create_table("http://x", "t", "p_1", "T", [])


def test_create_table_returns_id_when_present():
    with patch("init_schema.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"id": "mt_abc"}
        mock_post.return_value = mock_resp
        tid = init_schema.create_table("http://x", "t", "p_1", "T", [])
        assert tid == "mt_abc"


# --------------------------------------------------------------------------- #
# list_existing_tables：幂等查重的响应解析（B2）
# --------------------------------------------------------------------------- #
def test_list_existing_tables_parses_list_wrapper():
    with patch("init_schema.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"list": [{"title": "Projects"}, {"title": "Costs"}]}
        mock_get.return_value = mock_resp
        existing = init_schema.list_existing_tables("http://x", "t", "p_1")
        assert existing == {"Projects", "Costs"}


def test_list_existing_tables_parses_bare_array():
    with patch("init_schema.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = [{"title": "Projects"}]
        mock_get.return_value = mock_resp
        existing = init_schema.list_existing_tables("http://x", "t", "p_1")
        assert "Projects" in existing


def test_list_existing_tables_empty_response():
    with patch("init_schema.httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"list": []}
        mock_get.return_value = mock_resp
        assert init_schema.list_existing_tables("http://x", "t", "p_1") == set()
