"""day_range 边界测试（时区与范围正确性）。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from aggregator import CN_TZ


def _to_cn(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)


def test_day_range_specific_date():
    """指定日期：应覆盖该日 0:00 ~ 次日 0:00（整整一天）。"""
    from sync import day_range
    start_ts, end_ts, desc = day_range("2026-08-08", 1)
    start = datetime.fromtimestamp(start_ts, tz=CN_TZ)
    end = datetime.fromtimestamp(end_ts, tz=CN_TZ)
    assert start == _to_cn("2026-08-08")
    assert end == _to_cn("2026-08-09")
    assert desc == "2026-08-08"


def test_day_range_now_not_future():
    """默认 days 模式：结束时间是现在，开始时间在过去。"""
    from sync import day_range
    start_ts, end_ts, _ = day_range(None, 1)
    now = datetime.now(tz=CN_TZ).timestamp()
    assert start_ts <= now <= end_ts + 60  # 允许 1 分钟误差
