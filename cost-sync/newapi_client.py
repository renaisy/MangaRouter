"""New-API 日志拉取客户端。

从 New-API 的 /api/log 接口拉取 type=2（消费）日志，
支持按时间范围、分页拉全量。

字段参考：https://doc.newapi.pro/api/fei-log/
  items[].created_at      Unix 时间戳（秒）
  items[].quota           配额消耗（New-API 内部单位，需换算成元）
  items[].model_name      模型名
  items[].channel_id      渠道 ID
  items[].channel_name    渠道名
  items[].token_name      令牌名（可据此识别是哪个成员）
  items[].group           分组名
  items[].prompt_tokens   输入 tokens
  items[].completion_tokens 输出 tokens
  items[].type            日志类型，2=消费
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import httpx

QUOTA_PER_YUAN = 500_000  # New-API 默认 1 元 = 500000 配额（QuotaPerUnit），按实际改


def _to_int(v: Any, default: int = 0) -> int:
    """安全转 int：处理 None、空串、非数值字符串、bool 等边界情况。

    API 返回 JSON 的显式 null 会让 dict.get 返回 None，直接 int() 会 TypeError；
    布尔值 True 会被 int() 当成 1。这里统一兜底。
    """
    if v is None or isinstance(v, bool):
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@dataclass
class LogEntry:
    log_id: int
    created_at: int           # Unix 秒
    model_name: str
    channel_id: int
    channel_name: str
    token_name: str
    group: str
    quota: int                # 原始配额
    amount_yuan: float        # 换算后的元
    prompt_tokens: int
    completion_tokens: int


class NewAPIClient:
    """New-API 日志只读客户端。"""

    def __init__(self, base_url: str, token: str,
                 quota_per_yuan: int = QUOTA_PER_YUAN,
                 timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        # New-API 用 Authorization: Bearer <token>，管理员 token 可读全量日志
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        self.quota_per_yuan = quota_per_yuan

    def close(self) -> None:
        self._client.close()

    def quota_to_yuan(self, quota: int | float) -> float:
        """配额 → 元。"""
        if self.quota_per_yuan <= 0:
            return 0.0
        return round(float(quota) / self.quota_per_yuan, 4)

    def fetch_logs(
        self,
        start_timestamp: int,
        end_timestamp: int,
        *,
        log_type: int = 2,
        page_size: int = 100,
    ) -> Iterator[LogEntry]:
        """分页拉取指定时间范围内、指定类型的全部日志。

        用生成器逐条 yield，避免大时间范围一次性吃爆内存。
        """
        page = 1
        while True:
            r = self._client.get("/api/log", params={
                "p": page,
                "page_size": page_size,
                "type": log_type,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
            })
            r.raise_for_status()
            body = r.json()
            if not body.get("success"):
                raise RuntimeError(f"New-API 返回失败：{body.get('message')}")
            data = body.get("data") or {}
            items = data.get("items") or []
            if not items:
                return
            for it in items:
                # 显式 null（JSON 的 null）会让 dict.get 返回 None，int(None) 崩溃。
                # _to_int 统一兜底：None/非数值都返回默认值，避免单条脏数据让整页失败。
                quota_val = _to_int(it.get("quota"))
                yield LogEntry(
                    log_id=_to_int(it.get("id")),
                    created_at=_to_int(it.get("created_at")),
                    model_name=str(it.get("model_name") or ""),
                    channel_id=_to_int(it.get("channel_id")),
                    channel_name=str(it.get("channel_name") or ""),
                    token_name=str(it.get("token_name") or ""),
                    group=str(it.get("group") or ""),
                    quota=quota_val,
                    amount_yuan=self.quota_to_yuan(quota_val),
                    prompt_tokens=_to_int(it.get("prompt_tokens")),
                    completion_tokens=_to_int(it.get("completion_tokens")),
                )
            # 下一页
            total = _to_int(data.get("total"))
            if page * page_size >= total:
                return
            page += 1
