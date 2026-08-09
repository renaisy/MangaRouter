"""计费同步配置：从环境变量加载。

需要的环境变量（与项目根 .env 一致，可复用）：
  COST_NEWAPI_BASE_URL   New-API 地址，如 http://localhost:13000
  COST_NEWAPI_TOKEN      管理员令牌（需有日志读取权限）
  COST_NOCODB_BASE_URL   NocoDB 地址，如 http://localhost:18080
  COST_NOCODB_TOKEN      NocoDB API Token
  COST_NOCODB_TABLE_ID   Costs 表的 tableId（如 mt_xxxxx）
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, "").strip()


@dataclass(frozen=True)
class SyncConfig:
    newapi_base_url: str
    newapi_token: str
    nocodb_base_url: str
    nocodb_token: str
    nocodb_table_id: str

    @classmethod
    def from_env(cls) -> "SyncConfig":
        return cls(
            newapi_base_url=_env("COST_NEWAPI_BASE_URL", "http://localhost:13000"),
            newapi_token=_env("COST_NEWAPI_TOKEN"),
            nocodb_base_url=_env("COST_NOCODB_BASE_URL", "http://localhost:18080"),
            nocodb_token=_env("COST_NOCODB_TOKEN"),
            nocodb_table_id=_env("COST_NOCODB_TABLE_ID"),
        )

    def is_complete(self) -> bool:
        return all([self.newapi_token, self.nocodb_token, self.nocodb_table_id])


@lru_cache
def get_config() -> SyncConfig:
    return SyncConfig.from_env()
