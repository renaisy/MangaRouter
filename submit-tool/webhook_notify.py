"""审核通知 webhook（飞书/钉钉通用 JSON）。"""
from __future__ import annotations

import os
from typing import Any

import httpx


def notify_review(text: str, webhook_url: str | None = None) -> bool:
    url = (webhook_url or os.environ.get("REVIEW_WEBHOOK_URL", "")).strip()
    if not url:
        return False
    # 飞书自定义机器人 / 钉钉机器人 常见 text 格式；钉钉需加 msgtype
    payloads: list[dict[str, Any]] = [
        {"msg_type": "text", "content": {"text": text}},  # 飞书
        {"msgtype": "text", "text": {"content": text}},     # 钉钉
    ]
    try:
        with httpx.Client(timeout=15) as c:
            # 先试飞书结构；失败再试钉钉
            r = c.post(url, json=payloads[0])
            if r.status_code < 400:
                return True
            r2 = c.post(url, json=payloads[1])
            return r2.status_code < 400
    except Exception:
        return False
