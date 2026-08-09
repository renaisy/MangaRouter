"""提交指纹缓存：同 prompt+图+模型命中则复用已有成片。"""
from __future__ import annotations

import hashlib
import os
from typing import Any


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def cache_enabled() -> bool:
    return _env("SUBMIT_CACHE_ENABLED", "true").lower() in ("1", "true", "yes")


def submit_fingerprint(
    prompt: str,
    *,
    model: str = "",
    priority: str = "",
    image_urls: list[str] | None = None,
    project_key: str = "",
) -> str:
    urls = sorted(u.strip() for u in (image_urls or []) if u and u.strip())
    raw = "\n".join([
        project_key.strip(),
        priority.strip(),
        model.strip(),
        prompt.strip(),
        *urls,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_cached_success(nc: Any, fingerprint: str) -> dict[str, Any] | None:
    """在 NocoDB 中查找 Status=succeeded 且 Fingerprint 相同的记录。"""
    if not fingerprint or not hasattr(nc, "list_by_fingerprint"):
        return None
    rows = nc.list_by_fingerprint(fingerprint, status="succeeded", limit=1)
    return rows[0] if rows else None
