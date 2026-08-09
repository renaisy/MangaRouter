"""minio_store 安全相关单测。"""
from __future__ import annotations

import pytest

from minio_store import (
    sanitize_object_prefix,
    validate_image_url_for_submit,
    _host_is_private,
    _validate_video_download_url,
)


def test_sanitize_prefix_ok():
    assert sanitize_object_prefix("proj/ep1/shot-01") == "proj/ep1/shot-01"


def test_sanitize_prefix_rejects_traversal():
    with pytest.raises(ValueError):
        sanitize_object_prefix("../etc/passwd")
    with pytest.raises(ValueError):
        sanitize_object_prefix("a/b$/c")


def test_private_host():
    assert _host_is_private("127.0.0.1")
    assert _host_is_private("10.0.0.1")
    assert _host_is_private("minio")
    assert not _host_is_private("s3.example.com")


def test_image_url_requires_https_and_allowlist(monkeypatch):
    monkeypatch.setenv("SUBMIT_MINIO_PUBLIC_ENDPOINT", "s3.example.com")
    monkeypatch.delenv("SUBMIT_IMAGE_URL_ALLOW_HOSTS", raising=False)
    with pytest.raises(ValueError):
        validate_image_url_for_submit("http://s3.example.com/a.png")
    with pytest.raises(ValueError):
        validate_image_url_for_submit("https://evil.com/a.png")
    validate_image_url_for_submit("https://s3.example.com/storyboards/x.png")


def test_video_url_default_volc_allowlist():
    _validate_video_download_url("https://ark-content.volces.com/path/a.mp4")
    with pytest.raises(ValueError):
        _validate_video_download_url("https://evil.com/a.mp4")
    with pytest.raises(ValueError):
        _validate_video_download_url("http://ark-content.volces.com/a.mp4")
