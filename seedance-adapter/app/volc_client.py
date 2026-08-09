"""火山方舟 Seedance 异步任务客户端。

负责与火山方舟「创建任务 + 查询任务」原生异步接口交互。
参考：https://docs.volcengine.com/docs/82379/1520757

异步流程：
    1. POST /contents/generations/tasks   → 拿到 task_id
    2. GET  /contents/generations/tasks/{task_id}（轮询）
       status: queued -> running -> succeeded / failed
    3. succeeded 后 content.video_url 即为成片地址（有时效，需及时下载）

输入模式（靠 content 数组里的 image role 区分，文生视频/首帧/首尾帧/多参考图共用同一接口）：
    · 文生视频     [text]
    · 首帧图生视频 [text, image(role=first_frame)]
    · 首尾帧       [text, image(first_frame), image(last_frame)]   ← 首尾帧必填
    · 多参考图     [text, image(reference_image) ×N]               ← N 可达数十
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from .config import Settings


class ImageRole(str, Enum):
    """火山方舟 Seedance 图片在 content 数组中的角色。"""
    FIRST_FRAME = "first_frame"          # 首帧
    LAST_FRAME = "last_frame"            # 尾帧（首尾帧模式必填）
    REFERENCE_IMAGE = "reference_image"  # 参考图（多参考图模式）


@dataclass
class ImageInput:
    """一张输入图片。role 决定它是首帧/尾帧/参考图。"""
    url: str
    role: ImageRole = ImageRole.REFERENCE_IMAGE


class VolcError(RuntimeError):
    """火山方舟调用异常。"""


@dataclass
class TaskResult:
    task_id: str
    status: str                # queued / running / succeeded / failed
    video_url: str | None
    cover_url: str | None
    raw: dict[str, Any]
    error: str | None = None


class VolcClient:
    """火山方舟 Seedance 客户端（异步）。"""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._client = httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.volc_api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_task(
        self,
        model: str,
        prompt: str,
        *,
        images: list[ImageInput] | None = None,
        seed: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> str:
        """提交视频生成任务，返回 task_id。

        参数说明（与火山方舟一致）：
          model      模型名，如 doubao-seedance-2-0-fast
          prompt     文本提示词
          images     输入图片列表，每张带 role 决定模式：
                       [] 或 None            → 文生视频
                       [首帧]                 → 首帧图生视频
                       [首帧, 尾帧]           → 首尾帧图生视频（两 role 必填）
                       [参考图×N]             → 多参考图
                     也可混合，按火山方舟 content 数组语义透传。
          seed       随机种子（可选，便于复现）
          extra_params 透传给方舟的其它参数（如 watermark、duration）
        """
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in (images or []):
            content.append({
                "type": "image_url",
                "image_url": {"url": img.url},
                # role 是首尾帧/多参考图的关键标识
                "role": img.role.value,
            })

        payload: dict[str, Any] = {
            "model": model,
            "content": content,
        }
        if seed is not None:
            payload["seed"] = seed
        if extra_params:
            payload.update(extra_params)

        resp = await self._client.post(self.s.create_task_url, json=payload)
        data = self._parse(resp)
        task_id = data.get("id")
        if not task_id:
            raise VolcError(f"创建任务未返回 id：{data}")
        return str(task_id)

    async def get_task(self, task_id: str) -> TaskResult:
        """查询任务状态与结果（非阻塞，单次）。"""
        url = self.s.get_task_url_tpl.format(task_id=task_id)
        resp = await self._client.get(url)
        data = self._parse(resp)

        status = str(data.get("status", "unknown")).lower()
        content = data.get("content") or {}
        video_url = None
        cover_url = None
        # content 可能是 dict，里面 video_url / cover_url；也可能是 list
        if isinstance(content, dict):
            video_url = content.get("video_url")
            cover_url = content.get("cover_url")
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "video_url":
                        video_url = item.get("video_url")
                    if item.get("type") == "cover_url":
                        cover_url = item.get("cover_url")

        error = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else None
        return TaskResult(
            task_id=task_id,
            status=status,
            video_url=video_url,
            cover_url=cover_url,
            raw=data,
            error=error,
        )

    async def create_and_wait(self, *args: Any, **kwargs: Any) -> TaskResult:
        """提交任务并轮询直到完成/超时。便捷封装。参数透传给 create_task。"""
        task_id = await self.create_task(*args, **kwargs)
        deadline = time.time() + self.s.poll_max_seconds
        while time.time() < deadline:
            await asyncio.sleep(self.s.poll_interval_seconds)
            result = await self.get_task(task_id)
            if result.status in ("succeeded", "failed"):
                return result
        raise VolcError(f"任务 {task_id} 超时（>{self.s.poll_max_seconds}s）")

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise VolcError(f"方舟返回 HTTP {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except ValueError as e:
            # 2xx 但非 JSON（如某些网关返回 HTML 错误页），包装成 VolcError 而非冒泡成 500
            body_preview = resp.text[:200] if resp.text else "(空)"
            raise VolcError(f"方舟返回非 JSON 响应（{resp.headers.get('content-type')}）：{body_preview}") from e
