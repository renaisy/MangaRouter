"""NocoDB Storyboards 读写客户端。"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _escape_where_value(v: str) -> str:
    return f"'{str(v).replace(chr(39), chr(39)+chr(39))}'"


class NocoDBStoryboards:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        table_id: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or _env("NOCODB_BASE_URL", "http://localhost:18080")).rstrip("/")
        self.token = token or _env("NOCODB_TOKEN")
        self.table_id = table_id or _env("STORYBOARDS_TABLE_ID")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"xc-token": self.token},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def is_configured(self) -> bool:
        return bool(self.token and self.table_id)

    def list_by_status(self, status: str, limit: int = 100) -> list[dict[str, Any]]:
        where = quote(f"(Status,eq,{_escape_where_value(status)})")
        r = self._client.get(
            f"/api/v2/tables/{self.table_id}/records",
            params={"where": where, "limit": limit},
        )
        r.raise_for_status()
        return list((r.json() or {}).get("list") or [])

    def get_record(self, record_id: int | str) -> dict[str, Any] | None:
        r = self._client.get(f"/api/v2/tables/{self.table_id}/records/{record_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json() or None

    def patch_record(self, record_id: int | str, fields: dict[str, Any]) -> None:
        # NocoDB v2：PATCH /records + body 带 Id
        r = self._client.patch(
            f"/api/v2/tables/{self.table_id}/records",
            json={"Id": int(record_id), **fields},
        )
        r.raise_for_status()

    def record_id(self, row: dict[str, Any]) -> int | None:
        rid = row.get("Id") or row.get("id")
        return int(rid) if rid else None
