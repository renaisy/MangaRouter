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


def test_day_range_days_aligns_to_whole_days():
    """days 模式：按整天对齐。days=1 = 昨天 [昨0:00, 今0:00)，end 为今天 0:00。"""
    from sync import day_range
    start_ts, end_ts, desc = day_range(None, 1)
    today_0 = datetime.now(tz=CN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_0 = today_0 - timedelta(days=1)
    assert datetime.fromtimestamp(start_ts, tz=CN_TZ) == yesterday_0
    assert datetime.fromtimestamp(end_ts, tz=CN_TZ) == today_0
    assert desc == yesterday_0.strftime("%Y-%m-%d")  # 单天只显示日期


def test_day_range_multi_days():
    """days=3：覆盖过去 3 个完整自然日，描述用区间。"""
    from sync import day_range
    start_ts, end_ts, desc = day_range(None, 3)
    today_0 = datetime.now(tz=CN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    assert datetime.fromtimestamp(start_ts, tz=CN_TZ) == today_0 - timedelta(days=3)
    assert datetime.fromtimestamp(end_ts, tz=CN_TZ) == today_0
    assert "~" in desc  # 多天用区间描述
