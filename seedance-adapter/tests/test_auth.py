"""适配器鉴权测试。"""
from __future__ import annotations

import os

import pytest

os.environ["ADAPTER_API_TOKEN"] = "secret-token"
os.environ["ADAPTER_REQUIRE_AUTH"] = "true"
os.environ.setdefault("VOLC_API_KEY", "test")


@pytest.fixture()
def client(monkeypatch):
    from app.config import get_settings
    from app import main as main_mod
    from app.volc_client import TaskResult

    get_settings.cache_clear()

    class _Dummy:
        async def aclose(self):
            pass

        async def create_task(self, *a, **k):
            return "tid-1"

        async def get_task(self, task_id: str):
            return TaskResult(
                task_id=task_id, status="succeeded",
                video_url="https://x/a.mp4", cover_url=None, raw={},
            )

        async def create_and_wait(self, *a, **k):
            return await self.get_task("tid-1")

    # 跳过 lifespan 真实初始化：直接挂 dummy
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_lifespan(app):
        main_mod._client = _Dummy()
        yield
        main_mod._client = None

    monkeypatch.setattr(main_mod, "lifespan", fake_lifespan)
    # FastAPI 已绑定旧 lifespan；直接替换 app.router.lifespan_context
    main_mod.app.router.lifespan_context = fake_lifespan

    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c
    get_settings.cache_clear()


def test_health_no_auth(client):
    assert client.get("/health").status_code == 200


def test_create_requires_auth(client):
    r = client.post("/v1/videos", json={"model": "m", "prompt": "p"})
    assert r.status_code == 401


def test_create_with_auth(client):
    r = client.post(
        "/v1/videos",
        json={"model": "m", "prompt": "p"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == "tid-1"
