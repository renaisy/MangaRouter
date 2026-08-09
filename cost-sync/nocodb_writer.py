"""NocoDB Costs 表写入：把聚合行写入 Costs 表，带幂等去重。

去重策略：Costs 表用「日期 + 成员 + 模型 + 渠道 + 分组」作为业务唯一键
（与 aggregator.AggKey 的 5 字段严格一致，避免不同分组互相覆盖）。
同步时先查同键记录是否存在，存在则更新，不存在则插入。
避免重复运行导致数据翻倍。
"""
from __future__ import annotations

from typing import Iterable

import httpx

from aggregator import AggKey, AggValue


def _escape_where_value(v: str) -> str:
    """转义 NocoDB where 子句值里的语法特殊字符，防止过滤条件被破坏/注入。

    NocoDB where 语法以 , ~ ( ) 为分隔符，值里出现这些字符会破坏语义。
    这里把整段值用单引号包裹并对内部单引号转义，使其被当作字面字符串。
    """
    s = str(v)
    # 单引号转义：' -> ''（NocoDB/SQL 风格）
    s = s.replace("'", "''")
    return f"'{s}'"


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

    def _find_existing(self, date: str, member: str, model: str,
                       channel: str, group: str) -> int | None:
        """按业务唯一键（含 group）查已有记录，返回行 Id（无则 None）。"""
        from urllib.parse import quote
        # Date 字段用 exactDate 关键字（NocoDB v2 对 Date 的可工作语法，
        # eq + 日期串可能因底层时间分量匹配不上）
        where_raw = (
            f"(Date,exactDate,{_escape_where_value(date)})"
            f"~and(Member,eq,{_escape_where_value(member)})"
            f"~and(Model,eq,{_escape_where_value(model)})"
            f"~and(Channel,eq,{_escape_where_value(channel)})"
            f"~and(Group,eq,{_escape_where_value(group)})"
        )
        where = quote(where_raw)
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
        existing_id = self._find_existing(
            key.date, key.member, key.model, key.channel, key.group
        )
        if existing_id:
            # v2 官方契约：PATCH /records + body 带 Id（path 参数式 records/{id} 在 v2 有 404 bug）
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
        """批量 upsert，返回 {'inserted': n, 'updated': n, 'failed': n}。

        单行失败不阻断整体，但计入 failed，供调用方据此告警。
        """
        stats = {"inserted": 0, "updated": 0, "failed": 0}
        for key, val in items:
            try:
                stats[self.upsert(key, val, project)] += 1
            except Exception as e:
                # 单行失败不阻断整体，但必须计数
                stats["failed"] += 1
                print(f"[warn] 写入失败 {key}: {e}")
        return stats
