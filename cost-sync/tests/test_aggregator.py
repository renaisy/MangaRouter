"""计费同步单元测试。

重点测纯逻辑：配额换算、时区日期、聚合正确性、幂等去重。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from aggregator import AggKey, aggregate
from newapi_client import LogEntry, NewAPIClient
from nocodb_writer import NocoDBWriter


CN_TZ = timezone(timedelta(hours=8))


def _log(created_at: int, token: str = "张三", model: str = "doubao-seedance-2-0-fast",
         channel: str = "火山官方-fast", group: str = "standard",
         quota: int = 500_000, pt: int = 100, ct: int = 200) -> LogEntry:
    """构造一条日志。默认 quota=500000 = 1 元（按 QUOTA_PER_YUAN=500000）。"""
    return LogEntry(
        log_id=1, created_at=created_at, model_name=model,
        channel_id=1, channel_name=channel, token_name=token,
        group=group, quota=quota, amount_yuan=quota / 500_000,
        prompt_tokens=pt, completion_tokens=ct,
    )


# --------------------------------------------------------------------------- #
# 配额换算
# --------------------------------------------------------------------------- #
def test_quota_to_yuan_default():
    c = NewAPIClient("http://x", "t")
    assert c.quota_to_yuan(500_000) == 1.0
    assert c.quota_to_yuan(1_500_000) == 3.0
    assert c.quota_to_yuan(0) == 0.0
    c.close()


def test_quota_to_yuan_custom_unit():
    c = NewAPIClient("http://x", "t", quota_per_yuan=100_000)
    assert c.quota_to_yuan(100_000) == 1.0
    c.close()


# --------------------------------------------------------------------------- #
# 聚合
# --------------------------------------------------------------------------- #
def test_aggregate_groups_by_day_member_model_channel():
    # 同一天同模型同渠道同人的 3 条 + 不同模型 1 条
    ts = int(datetime(2026, 8, 8, 10, 0, tzinfo=CN_TZ).timestamp())
    entries = [
        _log(ts, token="张三", model="m1", channel="ch1", quota=500_000),   # 1元
        _log(ts + 60, token="张三", model="m1", channel="ch1", quota=500_000),  # 1元
        _log(ts + 120, token="张三", model="m1", channel="ch1", quota=500_000),  # 1元
        _log(ts, token="张三", model="m2", channel="ch1", quota=500_000),   # 1元
    ]
    agg = aggregate(entries)
    assert len(agg) == 2
    k1 = AggKey(date="2026-08-08", member="张三", model="m1", channel="ch1", group="standard")
    assert agg[k1].calls == 3
    assert agg[k1].amount_yuan == 3.0
    k2 = AggKey(date="2026-08-08", member="张三", model="m2", channel="ch1", group="standard")
    assert agg[k2].calls == 1


def test_aggregate_separates_members_and_days():
    ts1 = int(datetime(2026, 8, 8, 12, 0, tzinfo=CN_TZ).timestamp())
    ts2 = int(datetime(2026, 8, 9, 12, 0, tzinfo=CN_TZ).timestamp())
    entries = [
        _log(ts1, token="张三"),
        _log(ts1, token="李四"),  # 不同人
        _log(ts2, token="张三"),  # 不同天
    ]
    agg = aggregate(entries)
    assert len(agg) == 3
    dates = {k.date for k in agg}
    assert dates == {"2026-08-08", "2026-08-09"}


def test_aggregate_tokens_summed():
    ts = int(datetime(2026, 8, 8, tzinfo=CN_TZ).timestamp())
    entries = [
        _log(ts, pt=100, ct=200),
        _log(ts, pt=50, ct=150),
    ]
    agg = aggregate(entries)
    only = next(iter(agg.values()))
    assert only.prompt_tokens == 150
    assert only.completion_tokens == 350


def test_aggregate_empty():
    assert aggregate([]) == {}


# --------------------------------------------------------------------------- #
# NocoDB 写入幂等（用 mock）
# --------------------------------------------------------------------------- #
def test_upsert_inserts_when_not_exists():
    w = NocoDBWriter.__new__(NocoDBWriter)
    w.base_url = "http://x"
    w.table_id = "mt_test"
    w._client = MagicMock()

    # 第一次查：不存在
    w._client.get.return_value = MagicMock(json=lambda: {"list": []})
    w._client.post.return_value = MagicMock(raise_for_status=lambda: None)

    key = AggKey("2026-08-08", "张三", "m1", "ch1", "standard")
    from aggregator import AggValue
    res = w.upsert(key, AggValue(calls=2, prompt_tokens=10, completion_tokens=20, amount_yuan=1.5))
    assert res == "inserted"
    assert w._client.post.call_count == 1


def test_upsert_updates_when_exists():
    w = NocoDBWriter.__new__(NocoDBWriter)
    w.base_url = "http://x"
    w.table_id = "mt_test"
    w._client = MagicMock()

    # 查到已有记录 Id=42
    w._client.get.return_value = MagicMock(json=lambda: {"list": [{"Id": 42}]})
    w._client.patch.return_value = MagicMock(raise_for_status=lambda: None)

    key = AggKey("2026-08-08", "张三", "m1", "ch1", "standard")
    from aggregator import AggValue
    res = w.upsert(key, AggValue(calls=3, amount_yuan=2.0))
    assert res == "updated"
    # 应该 patch 而不是 post
    assert w._client.patch.call_count == 1
    assert w._client.post.call_count == 0
    # v0.3.2：v2 官方契约 PATCH /records + body 带 Id（path 式在 v2 有 404 bug）
    sent = w._client.patch.call_args.kwargs["json"]
    assert sent["Id"] == 42


def test_find_existing_where_includes_group():
    """去重键必须含 Group，否则不同分组互相覆盖（P0-2 回归保护）。"""
    w = NocoDBWriter.__new__(NocoDBWriter)
    w.base_url = "http://x"
    w.table_id = "mt_test"
    w._client = MagicMock()
    w._client.get.return_value = MagicMock(json=lambda: {"list": []},
                                           raise_for_status=lambda: None)

    w._find_existing("2026-08-08", "张三", "m1", "ch1", "final")
    sent_params = w._client.get.call_args.kwargs["params"]
    assert "Group" in sent_params["where"], "where 子句必须包含 Group 去重键"


def test_where_value_escaping():
    """where 值里的特殊字符必须被引号包裹转义（P0-2 注入修复）。"""
    from nocodb_writer import _escape_where_value
    assert _escape_where_value("standard") == "'standard'"
    escaped = _escape_where_value("火山官方,fast")
    assert escaped.startswith("'") and escaped.endswith("'")
    assert "," in escaped  # 原始逗号保留，但被引号包裹成字面量
    assert _escape_where_value("a'b") == "'a''b'"  # 单引号 SQL 风格转义


def test_upsert_many_counts_failures():
    """失败行必须计入 failed，供调用方告警（P2-6 修复）。"""
    w = NocoDBWriter.__new__(NocoDBWriter)
    w.base_url = "http://x"
    w.table_id = "mt_test"
    w._client = MagicMock()
    w._client.get.return_value = MagicMock(json=lambda: {"list": []})
    w._client.post.side_effect = RuntimeError("boom")

    from aggregator import AggValue
    items = [
        (AggKey("2026-08-08", "张三", "m1", "ch1", "standard"), AggValue(calls=1)),
        (AggKey("2026-08-08", "李四", "m2", "ch1", "draft"), AggValue(calls=1)),
    ]
    stats = w.upsert_many(items)
    assert stats["failed"] == 2
    assert stats["inserted"] == 0
    assert stats["updated"] == 0


# --------------------------------------------------------------------------- #
# v0.3.3 新增：created_at 异常跳过 + 一次性 round
# --------------------------------------------------------------------------- #
def test_aggregate_skips_invalid_created_at():
    """created_at<=0 的脏记录应跳过，不产生 1970 年的脏行。"""
    ts = int(datetime(2026, 8, 8, 12, 0, tzinfo=CN_TZ).timestamp())
    entries = [
        _log(ts),        # 正常
        _log(0),         # 异常：created_at=0
        _log(-1),        # 异常：负数
    ]
    agg = aggregate(entries)
    # 只有 1 条正常记录进了聚合，无 1970 年的行
    assert len(agg) == 1
    only = next(iter(agg.values()))
    assert only.calls == 1


def test_aggregate_rounds_once_not_incrementally():
    """金额应累加原始 float 最后一次性 round，避免逐步 round 累积偏差。

    构造会触发浮点误差的场景：0.1+0.2 != 0.3。
    """
    ts = int(datetime(2026, 8, 8, tzinfo=CN_TZ).timestamp())
    # 每条 quota=50000 → 0.1 元（按 QUOTA_PER_YUAN=500000）
    entries = [_log(ts, quota=50_000) for _ in range(3)]
    agg = aggregate(entries)
    only = next(iter(agg.values()))
    # 3 × 0.1 = 0.3，一次性 round 应精确等于 0.3（逐步 round 也碰巧对，这里主要防回归）
    assert only.amount_yuan == 0.3


# --------------------------------------------------------------------------- #
# v0.3.3 新增：fetch_logs 分页上限与异常包装（用 MockTransport）
# --------------------------------------------------------------------------- #
def test_fetch_logs_respects_max_pages(monkeypatch):
    """max_pages 上限应生效，防止 total 异常导致无限翻页。"""
    import json
    from newapi_client import NewAPIClient
    import httpx

    c = NewAPIClient("http://x", "t")
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # 每页都返回 1 条 + total=999999（诱使无限翻页）
        return httpx.Response(200, json={
            "success": True,
            "data": {"items": [{"id": 1, "created_at": 1700000000, "quota": 1000}],
                     "total": 999999},
        })

    # 替换 client 时必须保留 base_url（否则相对路径 /api/log 无法解析）
    c._client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler),
                             headers=dict(c._client.headers), timeout=5)
    try:
        list(c.fetch_logs(1, 2, max_pages=3))
        # 应该在 3 页后停止
        assert call_count["n"] == 3
    finally:
        c.close()


def test_fetch_logs_wraps_http_error():
    """4xx 应包装成 RuntimeError（可读提示），而非裸 HTTPStatusError 堆栈。"""
    from newapi_client import NewAPIClient
    import httpx

    c = NewAPIClient("http://x", "t")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    c._client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler),
                             headers=dict(c._client.headers), timeout=5)
    try:
        import pytest
        with pytest.raises(RuntimeError, match="拉日志失败 HTTP 401"):
            list(c.fetch_logs(1, 2))
    finally:
        c.close()
