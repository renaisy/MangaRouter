"""New-API 管理面客户端（v0.6.x）。

认证（AdminAuth）：
  Authorization: Bearer <用户系统 access_token>
  New-Api-User: <用户数字 ID>

渠道：GET/POST/PUT/DELETE /api/channel/
令牌：GET/POST/PUT/DELETE /api/token/（UserAuth，管理员用自己的 access token 即可）
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

# New-API common.ChannelType*
CHANNEL_TYPE_OPENAI = 1
CHANNEL_TYPE_CUSTOM = 8
CHANNEL_TYPE_VOLCENGINE = 45

CHANNEL_STATUS_ENABLED = 1
CHANNEL_STATUS_MANUAL_DISABLED = 2

KNOWN_GROUPS = frozenset({"draft", "standard", "final", "default"})


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def validate_group(group: str, *, allow_custom: bool = False) -> str:
    g = (group or "default").strip()
    if not g:
        raise ValueError("分组不能为空")
    if not allow_custom and g not in KNOWN_GROUPS:
        raise ValueError(f"未知分组 {g!r}；submit-tool 默认只认识 draft/standard/final")
    return g


def redact_key(key: str | None) -> str:
    if not key:
        return ""
    k = key.strip()
    if len(k) <= 8:
        return "****"
    return k[:4] + "…" + k[-4:]


@dataclass
class ChannelDraft:
    name: str
    type: int
    key: str
    models: str
    group: str = "default"
    base_url: str = ""
    weight: int = 100
    priority: int = 1
    status: int = CHANNEL_STATUS_ENABLED
    auto_ban: int = 1
    id: int | None = None

    def to_payload(self) -> dict[str, Any]:
        validate_group(self.group, allow_custom=True)
        payload: dict[str, Any] = {
            "name": self.name,
            "type": int(self.type),
            "key": self.key,
            "models": self.models,
            "group": self.group,
            "status": int(self.status),
            "weight": int(self.weight),
            "priority": int(self.priority),
            "auto_ban": int(self.auto_ban),
        }
        if self.base_url:
            payload["base_url"] = self.base_url.rstrip("/")
        if self.id is not None:
            payload["id"] = int(self.id)
        return payload


@dataclass
class NewAPIAdmin:
    base_url: str = field(default_factory=lambda: _env("ADMIN_NEWAPI_BASE_URL", "http://new-api:3000"))
    access_token: str = field(default_factory=lambda: _env("ADMIN_NEWAPI_TOKEN"))
    user_id: str = field(default_factory=lambda: _env("ADMIN_NEWAPI_USER_ID", "1"))
    timeout: int = 30

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.user_id)

    def _headers(self) -> dict[str, str]:
        tok = self.access_token
        if tok.lower().startswith("bearer "):
            auth = tok
        else:
            auth = f"Bearer {tok}"
        return {
            "Authorization": auth,
            "New-Api-User": str(self.user_id),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("未配置 ADMIN_NEWAPI_TOKEN / ADMIN_NEWAPI_USER_ID")
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.request(method, url, headers=self._headers(), **kwargs)
        try:
            body = r.json()
        except ValueError as e:
            raise RuntimeError(f"New-API 非 JSON 响应 HTTP {r.status_code}: {r.text[:200]}") from e
        if r.status_code == 401:
            raise RuntimeError(body.get("message") or "未授权：检查 access token 与 New-Api-User")
        if isinstance(body, dict) and body.get("success") is False:
            raise RuntimeError(body.get("message") or "New-API 返回失败")
        return body if isinstance(body, dict) else {"success": True, "data": body}

    def list_channels(self, page: int = 0, page_size: int = 100) -> list[dict[str, Any]]:
        body = self._request("GET", "/api/channel/", params={"p": page, "page_size": page_size})
        data = body.get("data") or []
        return list(data) if isinstance(data, list) else []

    def get_channel(self, channel_id: int) -> dict[str, Any]:
        body = self._request("GET", f"/api/channel/{channel_id}")
        return body.get("data") or {}

    def add_channel(self, draft: ChannelDraft) -> None:
        self._request("POST", "/api/channel/", json=draft.to_payload())

    def update_channel(self, draft: ChannelDraft) -> None:
        if draft.id is None:
            raise ValueError("更新渠道需要 id")
        self._request("PUT", "/api/channel/", json=draft.to_payload())

    def delete_channel(self, channel_id: int) -> None:
        self._request("DELETE", f"/api/channel/{channel_id}")

    def set_channel_status(self, channel: dict[str, Any], enabled: bool) -> None:
        """启用/禁用：PUT 完整渠道对象，改 status。"""
        status = CHANNEL_STATUS_ENABLED if enabled else CHANNEL_STATUS_MANUAL_DISABLED
        payload = dict(channel)
        payload["status"] = status
        # 列表接口可能省略 key；若无 key 则只改 status 可能失败——要求调用方先 get_channel
        self._request("PUT", "/api/channel/", json=payload)

    def test_channel(self, channel_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/channel/test/{channel_id}")

    def list_tokens(self, page: int = 0, size: int = 50) -> list[dict[str, Any]]:
        body = self._request("GET", "/api/token/", params={"p": page, "size": size})
        data = body.get("data") or []
        return list(data) if isinstance(data, list) else []

    def add_token(
        self,
        name: str,
        group: str = "draft,standard,final",
        *,
        remain_quota: int = 500000 * 500,  # 约 500 元（默认 QuotaPerUnit=500000）
        unlimited_quota: bool = False,
        expired_time: int = -1,
    ) -> dict[str, Any]:
        """创建令牌；成功后 data 可能不含明文 key——部分版本 Insert 后需再查。"""
        payload = {
            "name": name[:30],
            "group": group,
            "remain_quota": remain_quota,
            "unlimited_quota": unlimited_quota,
            "expired_time": expired_time,
            "model_limits_enabled": False,
            "model_limits": "",
        }
        body = self._request("POST", "/api/token/", json=payload)
        return body.get("data") or body

    def delete_token(self, token_id: int) -> None:
        self._request("DELETE", f"/api/token/{token_id}")
