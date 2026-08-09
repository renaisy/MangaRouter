"""VolcClient 单元测试：用 httpx.MockTransport 模拟方舟接口。"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.volc_client import ImageInput, ImageRole, VolcClient, VolcError


def _make_client(handler: Any) -> VolcClient:
    """构造一个把请求转发给 MockTransport 的客户端。"""
    s = Settings(
        volc_api_key="test-key",
        volc_base_url="https://ark.test/api/v3",
        poll_interval_seconds=0,
        poll_max_seconds=10,
        request_timeout_seconds=5,
        host="",
        port=0,
    )
    transport = httpx.MockTransport(handler)
    c = VolcClient(s)
    # 替换底层 transport
    c._client = httpx.AsyncClient(
        transport=transport,
        headers=c._client.headers,
        timeout=5,
    )
    return c


@pytest.mark.asyncio
async def test_create_task_returns_id() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v3/contents/generations/tasks"
        body = json.loads(req.content)
        assert body["model"] == "m1"
        assert body["content"][0]["text"] == "hello"
        return httpx.Response(200, json={"id": "task-123"})

    c = _make_client(handler)
    try:
        tid = await c.create_task(model="m1", prompt="hello")
        assert tid == "task-123"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_get_task_parses_dict_content() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "t1",
            "status": "succeeded",
            "content": {"video_url": "https://x/a.mp4", "cover_url": "https://x/c.jpg"},
        })

    c = _make_client(handler)
    try:
        r = await c.get_task("t1")
        assert r.status == "succeeded"
        assert r.video_url == "https://x/a.mp4"
        assert r.cover_url == "https://x/c.jpg"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_get_task_parses_list_content() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "t1",
            "status": "succeeded",
            "content": [
                {"type": "video_url", "video_url": "https://x/a.mp4"},
                {"type": "cover_url", "cover_url": "https://x/c.jpg"},
            ],
        })

    c = _make_client(handler)
    try:
        r = await c.get_task("t1")
        assert r.video_url == "https://x/a.mp4"
        assert r.cover_url == "https://x/c.jpg"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_create_and_wait_terminal_status() -> None:
    """轮询到 succeeded 立即返回。"""
    calls = {"n": 0}

    async def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(200, json={"id": "t1"})
        # GET 查询
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(200, json={"id": "t1", "status": "running"})
        return httpx.Response(200, json={
            "id": "t1", "status": "succeeded",
            "content": {"video_url": "https://x/a.mp4"},
        })

    c = _make_client(handler)
    try:
        r = await c.create_and_wait(model="m", prompt="p")
        assert r.status == "succeeded"
        assert r.video_url == "https://x/a.mp4"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_error_raises_volc_error() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    c = _make_client(handler)
    try:
        with pytest.raises(VolcError):
            await c.create_task(model="m", prompt="p")
    finally:
        await c.aclose()


# --------------------------------------------------------------------------- #
# 多图能力测试：首尾帧 / 多参考图（v0.2 新增）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_first_last_frame_builds_two_image_content() -> None:
    """首尾帧：content 应包含 text + 2 张图（role 分别为 first_frame / last_frame）。"""
    captured: dict[str, Any] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "flf-1"})

    c = _make_client(handler)
    try:
        tid = await c.create_task(
            model="doubao-seedance-2-0",
            prompt="镜头从少女推到月亮",
            images=[
                ImageInput(url="https://x/first.jpg", role=ImageRole.FIRST_FRAME),
                ImageInput(url="https://x/last.jpg", role=ImageRole.LAST_FRAME),
            ],
        )
        assert tid == "flf-1"
        body = captured["body"]
        # 应为 text + 2 张图
        assert len(body["content"]) == 3
        assert body["content"][0] == {"type": "text", "text": "镜头从少女推到月亮"}
        imgs = body["content"][1:]
        assert imgs[0]["role"] == "first_frame"
        assert imgs[0]["image_url"]["url"] == "https://x/first.jpg"
        assert imgs[1]["role"] == "last_frame"
        assert imgs[1]["image_url"]["url"] == "https://x/last.jpg"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_multiple_reference_images_preserves_order() -> None:
    """多参考图：N 张图都应是 reference_image，顺序保留。"""
    captured: dict[str, Any] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "ref-1"})

    c = _make_client(handler)
    try:
        await c.create_task(
            model="doubao-seedance-2-5-pro",
            prompt="角色 A 在场景 B 中奔跑",
            images=[
                ImageInput("https://x/char_a.jpg"),
                ImageInput("https://x/scene_b.jpg"),
                ImageInput("https://x/pose.jpg"),
            ],
        )
        imgs = captured["body"]["content"][1:]
        assert len(imgs) == 3
        assert all(im["role"] == "reference_image" for im in imgs)
        assert [im["image_url"]["url"] for im in imgs] == [
            "https://x/char_a.jpg", "https://x/scene_b.jpg", "https://x/pose.jpg",
        ]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_text_only_has_no_images() -> None:
    """纯文生视频：content 只有 text，没有图片元素。"""
    captured: dict[str, Any] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "t2v-1"})

    c = _make_client(handler)
    try:
        await c.create_task(model="m", prompt="日落", images=None)
        assert captured["body"]["content"] == [{"type": "text", "text": "日落"}]
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_first_frame_only_single_image() -> None:
    """仅首帧：content 为 text + 1 张 first_frame 图。"""
    captured: dict[str, Any] = {}

    async def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"id": "f2v-1"})

    c = _make_client(handler)
    try:
        await c.create_task(
            model="m", prompt="延续动作",
            images=[ImageInput("https://x/start.jpg", ImageRole.FIRST_FRAME)],
        )
        imgs = captured["body"]["content"][1:]
        assert len(imgs) == 1
        assert imgs[0]["role"] == "first_frame"
    finally:
        await c.aclose()
