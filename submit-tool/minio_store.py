"""MinIO 上传 / 预签名 / 成片归档。"""
from __future__ import annotations

import io
import ipaddress
import os
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse

from minio import Minio

_ALLOWED_IMG_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMG_BYTES = 20 * 1024 * 1024
_MAX_VIDEO_BYTES = int(os.environ.get("SUBMIT_MAX_VIDEO_BYTES", str(500 * 1024 * 1024)))
_SAFE_PREFIX_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def minio_client(
    endpoint: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    secure: bool | None = None,
) -> Minio:
    ep = endpoint or _env("SUBMIT_MINIO_ENDPOINT", "localhost:19000")
    ak = access_key or _env("SUBMIT_MINIO_ACCESS_KEY", "seedance-admin")
    sk = secret_key or _env("SUBMIT_MINIO_SECRET_KEY", "")
    sec = _env("SUBMIT_MINIO_SECURE", "false").lower() == "true" if secure is None else secure
    return Minio(ep, access_key=ak, secret_key=sk, secure=sec)


def _public_endpoint() -> tuple[str, bool]:
    """方舟可访问的公网 Host（无 scheme）与是否 HTTPS。"""
    pub = _env("SUBMIT_MINIO_PUBLIC_ENDPOINT")
    if not pub:
        raise RuntimeError(
            "未配置 SUBMIT_MINIO_PUBLIC_ENDPOINT：生产必须用公网 Host 签名，禁止内网 Host 改写"
        )
    pub = pub.replace("https://", "").replace("http://", "").rstrip("/")
    secure = _env("SUBMIT_MINIO_PUBLIC_SECURE", "true").lower() == "true"
    return pub, secure


def public_presign_client() -> Minio:
    """用于生成方舟可拉取的预签名 URL（Host = 公网域名）。"""
    pub, secure = _public_endpoint()
    ak = _env("SUBMIT_MINIO_ACCESS_KEY", "seedance-admin")
    sk = _env("SUBMIT_MINIO_SECRET_KEY", "")
    return Minio(pub, access_key=ak, secret_key=sk, secure=secure)


def sanitize_object_prefix(prefix: str) -> str:
    """仅允许安全路径段，防 ../ 注入。"""
    raw = prefix.replace("\\", "/")
    if ".." in raw.split("/"):
        raise ValueError("路径不允许包含 ..")
    parts = [p for p in raw.split("/") if p and p != "."]
    clean = []
    for p in parts:
        if not _SAFE_PREFIX_RE.match(p):
            raise ValueError(f"非法路径段：{p!r}")
        clean.append(p)
    if not clean:
        return "default"
    return "/".join(clean)


def _host_is_private(hostname: str) -> bool:
    host = hostname.split(":")[0]
    if host in ("localhost", "metadata.google.internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        # 主机名：拦截明显内网/docker
        lowered = host.lower()
        if lowered.endswith(".local") or lowered.endswith(".internal"):
            return True
        if lowered in ("minio", "new-api", "nocodb", "mysql-newapi", "mysql-nocodb",
                       "seedance-adapter", "host.docker.internal"):
            return True
        return False


def validate_image_url_for_submit(url: str) -> None:
    """批量 ImageUrl：仅允许 https，且 Host 为本项目公网 MinIO（或显式白名单）。"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("ImageUrl 仅允许 https")
    if not parsed.hostname or _host_is_private(parsed.hostname):
        raise ValueError("ImageUrl Host 非法或指向私网")
    allow = _env("SUBMIT_IMAGE_URL_ALLOW_HOSTS")
    if allow:
        allowed = {h.strip().lower() for h in allow.split(",") if h.strip()}
    else:
        pub, _ = _public_endpoint()
        allowed = {pub.split(":")[0].lower()}
    if parsed.hostname.lower() not in allowed:
        raise ValueError(f"ImageUrl Host 不在白名单：{parsed.hostname}")


def _validate_video_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("成片下载仅允许 https")
    if not parsed.hostname or _host_is_private(parsed.hostname):
        raise ValueError("成片 URL Host 非法或指向私网")
    host = parsed.hostname.lower()
    allow = _env("SUBMIT_VIDEO_URL_ALLOW_HOSTS")
    if allow:
        allowed = {h.strip().lower() for h in allow.split(",") if h.strip()}
    else:
        # 默认：火山方舟常见成片域名后缀
        allowed = {"*.volces.com", "*.volcengineapi.com", "*.byteimg.com", "*.toutiao.com"}
    ok = False
    for a in allowed:
        if a.startswith("*."):
            if host == a[2:] or host.endswith("." + a[2:]):
                ok = True
                break
        elif host == a:
            ok = True
            break
    if not ok:
        raise ValueError(f"成片 URL Host 不在白名单：{host}")


def upload_image_bytes(
    data: bytes,
    suffix: str,
    content_type: str = "image/png",
    bucket: str = "storyboards",
    client: Minio | None = None,
) -> str:
    """上传图片并返回公网预签名 GET URL。"""
    suffix = suffix.lower()
    if suffix not in _ALLOWED_IMG_SUFFIXES:
        raise ValueError(f"不支持的图片格式 {suffix}，仅支持 {sorted(_ALLOWED_IMG_SUFFIXES)}")
    if len(data) > _MAX_IMG_BYTES:
        raise ValueError(f"图片过大（{len(data)/1024/1024:.1f}MB），上限 {_MAX_IMG_BYTES/1024/1024:.0f}MB")

    object_name = f"uploads/{datetime.now():%Y%m%d}/{uuid.uuid4().hex}{suffix}"
    c = client or minio_client()
    c.put_object(bucket, object_name, io.BytesIO(data), length=len(data), content_type=content_type)

    seconds = int(_env("SUBMIT_MINIO_PRESIGN_SECONDS", "7200"))
    pc = public_presign_client()
    return pc.presigned_get_object(bucket, object_name, expires=timedelta(seconds=seconds))


def upload_streamlit_file(uploaded_file, bucket: str = "storyboards", client: Minio | None = None) -> str:
    raw_name = str(getattr(uploaded_file, "name", ""))
    suffix = os.path.splitext(raw_name)[1].lower() or ".png"
    data = uploaded_file.getvalue()
    ctype = getattr(uploaded_file, "type", None) or "image/png"
    return upload_image_bytes(data, suffix, ctype, bucket=bucket, client=client)


def archive_video_from_url(
    video_url: str,
    object_prefix: str,
    bucket: str = "outputs",
    client: Minio | None = None,
    share_days: int = 2,
) -> tuple[str, str]:
    """下载方舟成片到 MinIO，返回 (minio_path, share_url)。含 SSRF/体积防护。"""
    import httpx

    _validate_video_download_url(video_url)
    prefix = sanitize_object_prefix(object_prefix)
    c = client or minio_client()
    object_name = f"{prefix}/{uuid.uuid4().hex}.mp4"

    max_redirects = 3
    with httpx.Client(timeout=120, follow_redirects=True, max_redirects=max_redirects) as hx:
        with hx.stream("GET", video_url) as r:
            r.raise_for_status()
            cl = r.headers.get("content-length")
            if cl and int(cl) > _MAX_VIDEO_BYTES:
                raise ValueError(f"成片过大（Content-Length={cl}）")
            buf = io.BytesIO()
            total = 0
            for chunk in r.iter_bytes():
                total += len(chunk)
                if total > _MAX_VIDEO_BYTES:
                    raise ValueError(f"成片超过上限 {_MAX_VIDEO_BYTES} bytes")
                buf.write(chunk)
            data = buf.getvalue()

    c.put_object(bucket, object_name, io.BytesIO(data), length=len(data), content_type="video/mp4")
    minio_path = f"{bucket}/{object_name}"
    pc = public_presign_client()
    share = pc.presigned_get_object(bucket, object_name, expires=timedelta(days=share_days))
    return minio_path, share
