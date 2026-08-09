"""submit-tool 单元测试。"""
from __future__ import annotations

from newapi_submit import (
    default_model_for,
    group_for_priority,
    token_for_group,
    _headers,
)
from nocodb_client import _escape_where_value


def test_group_for_priority():
    assert group_for_priority("草稿") == "draft"
    assert group_for_priority("成片") == "final"
    assert group_for_priority("unknown") == "standard"


def test_default_model():
    assert "mini" in default_model_for("草稿")
    assert "fast" in default_model_for("日常")


def test_token_for_group(monkeypatch):
    monkeypatch.setenv("SUBMIT_NEWAPI_TOKEN", "default")
    monkeypatch.setenv("SUBMIT_TOKEN_DRAFT", "draft-tok")
    assert token_for_group("draft") == "draft-tok"
    assert token_for_group("standard") == "default"


def test_headers_include_group():
    h = _headers("tok", "draft")
    assert h["Authorization"] == "Bearer tok"
    assert h["X-New-Api-Group"] == "draft"
    assert "extra_params" not in h


def test_escape_where():
    assert _escape_where_value("a'b") == "'a''b'"
