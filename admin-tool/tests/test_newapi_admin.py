"""admin-tool 单测。"""
from __future__ import annotations

import httpx
import pytest

from newapi_admin import (
    ChannelDraft,
    NewAPIAdmin,
    redact_key,
    validate_group,
)
from templates_presets import manga_triple_presets


def test_validate_group_ok():
    assert validate_group("draft") == "draft"


def test_validate_group_rejects_unknown():
    with pytest.raises(ValueError):
        validate_group("projectA")


def test_validate_group_allow_custom():
    assert validate_group("projectA", allow_custom=True) == "projectA"


def test_redact_key():
    assert "…" in redact_key("sk-abcdefghijklmnop")
    assert redact_key("short") == "****"


def test_channel_draft_payload():
    d = ChannelDraft(
        name="t",
        type=8,
        key="secret",
        models="m1",
        group="draft",
        base_url="http://seedance-adapter:18008/",
        weight=100,
        priority=1,
    )
    p = d.to_payload()
    assert p["base_url"] == "http://seedance-adapter:18008"
    assert p["group"] == "draft"
    assert "id" not in p


def test_manga_presets_count():
    drafts = manga_triple_presets(volc_api_key="k", use_adapter=True)
    assert len(drafts) == 4
    assert {d.group for d in drafts} == {"draft", "standard", "final"}
    assert all(d.base_url.endswith("18008") for d in drafts)


def test_manga_presets_with_aggregator():
    drafts = manga_triple_presets(
        volc_api_key="k",
        aggregator_api_key="agg",
        aggregator_base_url="https://agg.example/v1",
    )
    assert len(drafts) == 5
    assert drafts[-1].group == "draft"
    assert drafts[-1].weight == 30


def test_list_channels_mock(httpx_mock=None):
    """用 httpx MockTransport。"""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("New-Api-User") == "1"
        assert "Bearer" in request.headers.get("Authorization", "")
        assert request.url.path == "/api/channel/"
        return httpx.Response(200, json={
            "success": True,
            "data": [{"id": 1, "name": "c1", "group": "draft", "key": "secretkey123"}],
        })

    transport = httpx.MockTransport(handler)
    admin = NewAPIAdmin(
        base_url="http://new-api:3000",
        access_token="atok",
        user_id="1",
    )

    # 临时替换：直接测 _request 路径
    def _request(method, path, **kwargs):
        with httpx.Client(transport=transport, base_url=admin.base_url) as c:
            r = c.request(method, path, headers=admin._headers(), **kwargs)
            return r.json()

    admin._request = _request  # type: ignore
    rows = admin.list_channels()
    assert rows[0]["name"] == "c1"


def test_add_channel_posts_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(200, json={"success": True, "message": ""})

    transport = httpx.MockTransport(handler)
    admin = NewAPIAdmin(base_url="http://n", access_token="t", user_id="1")

    def _request(method, path, **kwargs):
        with httpx.Client(transport=transport, base_url="http://n") as c:
            r = c.request(method, path, headers=admin._headers(), **kwargs)
            body = r.json()
            if body.get("success") is False:
                raise RuntimeError(body.get("message"))
            return body

    admin._request = _request  # type: ignore
    admin.add_channel(ChannelDraft(name="x", type=8, key="k", models="m", group="draft"))
    assert seen["path"] == "/api/channel/"
