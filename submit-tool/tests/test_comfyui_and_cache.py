"""comfyui_bridge / submit_cache / worker 窗口单测。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from comfyui_bridge import ComfyUIBridge, ComfyUIError, fill_template
from minio_store import project_object_prefix
from submit_cache import submit_fingerprint
from worker import within_active_hours


def test_fill_template_strips_meta_and_replaces():
    tpl = {
        "_comment": "doc only",
        "_how_to_use": ["x"],
        "1": {"class_type": "LoadImage", "inputs": {"image": "{{first_frame_img}}"}},
        "2": {"inputs": {"prompt": "hello {{name}}"}},
    }
    out = fill_template(tpl, {"first_frame_img": "a.png", "name": "world"})
    assert "_comment" not in out
    assert out["1"]["inputs"]["image"] == "a.png"
    assert out["2"]["inputs"]["prompt"] == "hello world"


def test_output_urls_encode(monkeypatch):
    bridge = ComfyUIBridge("http://comfy.example:8188")
    entry = {
        "outputs": {
            "9": {
                "gifs": [{"filename": "a b.mp4", "subfolder": "sub/x", "type": "output"}],
            }
        }
    }
    urls = bridge.output_urls(entry)
    assert len(urls) == 1
    assert "a%20b.mp4" in urls[0]
    assert "sub%2Fx" in urls[0]
    bridge.close()


def test_wait_result_raises_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "pid1": {
                "status": {
                    "completed": True,
                    "status_str": "error",
                    "messages": [{"data": {"error_message": "boom"}}],
                }
            }
        })

    transport = httpx.MockTransport(handler)
    bridge = ComfyUIBridge("http://comfy")
    bridge._client = httpx.Client(transport=transport, base_url="http://comfy")
    with pytest.raises(ComfyUIError, match="boom"):
        bridge.wait_result("pid1", max_seconds=1, interval=0)
    bridge.close()


def test_project_object_prefix():
    assert project_object_prefix("showA", "ep1", "s01") == "projects/showA/ep1/s01"
    assert project_object_prefix("a/b", "x") == "projects/a/x"
    with pytest.raises(ValueError):
        project_object_prefix("../x")


def test_submit_fingerprint_stable():
    a = submit_fingerprint("p", model="m", priority="日常", image_urls=["u2", "u1"], project_key="k")
    b = submit_fingerprint("p", model="m", priority="日常", image_urls=["u1", "u2"], project_key="k")
    assert a == b
    c = submit_fingerprint("p2", model="m", priority="日常", image_urls=["u1"], project_key="k")
    assert a != c


def test_within_active_hours(monkeypatch):
    monkeypatch.setenv("WORKER_ACTIVE_HOURS", "9-18")
    tz = ZoneInfo("Asia/Shanghai")
    assert within_active_hours(datetime(2026, 8, 9, 10, tzinfo=tz))
    assert not within_active_hours(datetime(2026, 8, 9, 8, tzinfo=tz))
    monkeypatch.setenv("WORKER_ACTIVE_HOURS", "")
    assert within_active_hours(datetime(2026, 8, 9, 3, tzinfo=tz))
