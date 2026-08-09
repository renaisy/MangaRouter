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
    # v0.3.1：Id 走 path 参数（PATCH .../records/{id}），不在 body 里
    patch_url = w._client.patch.call_args.args[0]
    assert "/records/42" in patch_url


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
