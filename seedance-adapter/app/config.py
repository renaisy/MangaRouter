"""配置读取：从环境变量加载，缺失时给出友好提示。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


@dataclass(frozen=True)
class Settings:
    # 火山方舟（Volcengine ARK）
    volc_api_key: str
    volc_base_url: str  # 例如 https://ark.cn-beijing.volces.com/api/v3

    # 轮询与超时
    poll_interval_seconds: int   # 查询任务结果间隔
    poll_max_seconds: int        # 单任务最长等待

    # HTTP
    request_timeout_seconds: int

    # 监听
    host: str
    port: int

    @property
    def create_task_url(self) -> str:
        return f"{self.volc_base_url}/contents/generations/tasks"

    @property
    def get_task_url_tpl(self) -> str:
        # {task_id} 占位
        return f"{self.volc_base_url}/contents/generations/tasks/{{task_id}}"


@lru_cache
def get_settings() -> Settings:
    api_key = _env("VOLC_API_KEY")
    if not api_key:
        # 不抛异常，便于容器先起来再在 .env 里补 key
        print("[config] 警告：未设置 VOLC_API_KEY，请在 .env 中配置火山引擎方舟 API Key")
    return Settings(
        volc_api_key=api_key,
        volc_base_url=_env("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        poll_interval_seconds=int(_env("POLL_INTERVAL_SECONDS", "8")),
        poll_max_seconds=int(_env("POLL_MAX_SECONDS", "900")),
        request_timeout_seconds=int(_env("REQUEST_TIMEOUT_SECONDS", "60")),
        host=_env("HOST", "0.0.0.0"),
        port=int(_env("ADAPTER_PORT", "18008")),
    )
