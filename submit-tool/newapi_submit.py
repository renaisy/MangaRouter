"""经 New-API 提交 / 查询 Seedance 任务。"""
from __future__ import annotations

import os
from typing import Any

import httpx

PRIORITY_TO_GROUP = {
    "草稿": "draft", "日常": "standard", "成片": "final",
    "draft": "draft", "standard": "standard", "final": "final",
}


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def group_for_priority(priority: str) -> str:
    return PRIORITY_TO_GROUP.get(priority, "standard")


def token_for_group(group: str, default_token: str = "") -> str:
    """按分组选令牌；未配置分档令牌时回退默认。"""
    mapping = {
        "draft": _env("SUBMIT_TOKEN_DRAFT"),
        "standard": _env("SUBMIT_TOKEN_STANDARD"),
        "final": _env("SUBMIT_TOKEN_FINAL"),
    }
    return mapping.get(group) or default_token or _env("SUBMIT_NEWAPI_TOKEN")


def default_model_for(priority: str) -> str:
    group = group_for_priority(priority)
    return {
        "draft": "doubao-seedance-2-0-mini",
        "standard": "doubao-seedance-2-0-fast",
        "final": "doubao-seedance-2-0",
    }.get(group, "doubao-seedance-2-0-fast")


def _headers(token: str, group: str) -> dict[str, str]:
    # New-API：令牌绑定分组；多分组令牌可用 X-New-Api-Group 指定（常见 fork/版本）
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-New-Api-Group": group,
    }


def submit_async(
    base_url: str,
    token: str,
    *,
    model: str,
    prompt: str,
    images: list[dict] | None,
    group: str,
    timeout: int = 60,
) -> dict[str, Any]:
    """POST /v1/videos → {id}。不把 group 放进会透传方舟的 extra_params。"""
    url = f"{base_url.rstrip('/')}/v1/videos"
    payload: dict[str, Any] = {"model": model, "prompt": prompt}
    if images:
        payload["images"] = images
    r = httpx.post(url, headers=_headers(token, group), json=payload, timeout=timeout)
    if r.status_code >= 400:
        return {"status": "failed", "error": f"HTTP {r.status_code}: {r.text}", "id": None}
    data = r.json()
    return {"status": "queued", "id": data.get("id"), "error": None}


def get_task(base_url: str, token: str, task_id: str, group: str = "standard", timeout: int = 30) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/videos/{task_id}"
    r = httpx.get(url, headers=_headers(token, group), timeout=timeout)
    if r.status_code >= 400:
        return {"status": "failed", "error": f"HTTP {r.status_code}: {r.text}", "video_url": None}
    return r.json()


def submit_sync(
    base_url: str,
    token: str,
    *,
    model: str,
    prompt: str,
    images: list[dict] | None,
    group: str,
    timeout: int = 900,
) -> dict[str, Any]:
    """兼容旧路径：同步等待。优先用于调试；生产走 submit_async + worker。"""
    url = f"{base_url.rstrip('/')}/v1/videos/sync"
    payload: dict[str, Any] = {"model": model, "prompt": prompt}
    if images:
        payload["images"] = images
    r = httpx.post(url, headers=_headers(token, group), json=payload, timeout=timeout)
    if r.status_code >= 400:
        return {"status": "failed", "error": f"HTTP {r.status_code}: {r.text}", "video_url": None}
    return r.json()
