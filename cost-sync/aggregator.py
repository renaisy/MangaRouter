"""日志聚合：把逐条日志按「日 × 模型 × 渠道 × 分组 × 成员」聚合成汇总行。

聚合粒度选择说明：
  · 按调用明细同步 → 数据细但会刷爆 NocoDB（万级/天）
  · 按日汇总同步 → 每天几十行，适合成本看板，推荐

聚合 key：(日期, 成员, 模型, 渠道, 分组)
聚合值：调用次数、tokens 合计、花费合计
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Iterable

from newapi_client import LogEntry

# 国内时区，New-API created_at 是 Unix 秒
CN_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class AggKey:
    date: str          # YYYY-MM-DD
    member: str        # token_name，即成员标识
    model: str
    channel: str       # channel_name
    group: str


@dataclass
class AggValue:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    amount_yuan: float = 0.0


def aggregate(entries: Iterable[LogEntry]) -> dict[AggKey, AggValue]:
    """把日志流聚合成 {AggKey: AggValue}。"""
    result: dict[AggKey, AggValue] = defaultdict(AggValue)
    for e in entries:
        date = datetime.fromtimestamp(e.created_at, tz=CN_TZ).strftime("%Y-%m-%d")
        key = AggKey(
            date=date,
            member=e.token_name,
            model=e.model_name,
            channel=e.channel_name,
            group=e.group,
        )
        v = result[key]
        v.calls += 1
        v.prompt_tokens += e.prompt_tokens
        v.completion_tokens += e.completion_tokens
        v.amount_yuan = round(v.amount_yuan + e.amount_yuan, 4)
    return dict(result)
