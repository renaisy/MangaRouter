"""NocoDB Costs 表写入：把聚合行写入 Costs 表，带幂等去重。

去重策略：Costs 表用「日期 + 成员 + 模型 + 渠道」作为业务唯一键。
同步时先查同键记录是否存在，存在则更新（累加/覆盖），不存在则插入。
避免重复运行导致数据翻倍。
"""
from __future__ import annotations

from typing import Iterable

import httpx

from aggregator import AggKey, AggValue


class NocoDBWriter:
    """NocoDB v2 API 写入器。"""

    def __init__(self, base_url: str, token: str, table_id: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.table_id = table_id
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"xc-token": token},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def _find_existing(self, date: str, member: str, model: str, channel: str) -> int | None:
        """按业务唯一键查已有记录，返回行 Id（无则 None）。"""
        from urllib.parse import quote
        where = quote(
            f"(Date,eq,{date})~and(Member,eq,{member})"
            f"~and(Model,eq,{model})~and(Channel,eq,{channel})"
        )
        r = self._client.get(f"/api/v2/tables/{self.table_id}/records",
                             params={"where": where, "limit": 1})
        r.raise_for_status()
        rows = (r.json() or {}).get("list") or []
        if not rows:
            return None
        first = rows[0]
        return int(first.get("Id") or first.get("id") or 0) or None

    def upsert(self, key: AggKey, val: AggValue, project: str = "") -> str:
        """插入或更新一行成本汇总。返回 'inserted' / 'updated'。"""
        fields = {
            "Date": key.date,
            "Project": project,
            "Member": key.member,
            "Channel": key.channel,
            "Model": key.model,
            "Group": key.group,
            "Calls": val.calls,
            "Tokens": val.prompt_tokens + val.completion_tokens,
            "Amount": val.amount_yuan,
        }
        existing_id = self._find_existing(key.date, key.member, key.model, key.channel)
        if existing_id:
            r = self._client.patch(
                f"/api/v2/tables/{self.table_id}/records",
                json={"Id": existing_id, **fields},
            )
            r.raise_for_status()
            return "updated"
        r = self._client.post(
            f"/api/v2/tables/{self.table_id}/records",
            json=fields,
        )
        r.raise_for_status()
        return "inserted"

    def upsert_many(self, items: Iterable[tuple[AggKey, AggValue]],
                    project: str = "") -> dict[str, int]:
        """批量 upsert，返回 {'inserted': n, 'updated': n}。"""
        stats = {"inserted": 0, "updated": 0}
        for key, val in items:
            try:
                stats[self.upsert(key, val, project)] += 1
            except Exception as e:
                # 单行失败不阻断整体
                print(f"[warn] 写入失败 {key}: {e}")
        return stats
