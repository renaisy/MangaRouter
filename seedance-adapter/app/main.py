"""Seedance 异步适配器 —— FastAPI 应用。

提供两套接口：
  1) 方舟原生异步风格（与火山官方一致）：
       POST /v1/videos           提交任务 -> {id}
       GET  /v1/videos/{task_id} 查询任务 -> {status, content.video_url...}
  2) 同步阻塞风格（便于 New-API / 简单客户端直接调用）：
       POST /v1/videos/sync      提交并等待结果 -> {video_url}

部署：见 ../Dockerfile
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import get_settings
from .volc_client import ImageInput, ImageRole, VolcClient, VolcError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("seedance-adapter")

_client: VolcClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建客户端，退出时关闭。"""
    global _client
    settings = get_settings()
    _client = VolcClient(settings)
    log.info("Seedance 适配器已启动，监听 %s:%s", settings.host, settings.port)
    if not settings.volc_api_key:
        log.warning("VOLC_API_KEY 未配置，调用将失败，请在 .env 中设置")
    yield
    # 判空：启动期若构造失败，_client 仍为 None，shutdown 时不能 None.aclose()
    if _client is not None:
        await _client.aclose()
    _client = None


app = FastAPI(
    title="Seedance 异步适配器",
    description="把火山方舟 Seedance 异步视频生成任务包装为统一 HTTP 接口",
    version="0.1.0",
    lifespan=lifespan,
)


def client() -> VolcClient:
    if _client is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="客户端未就绪")
    return _client


# --------------------------------------------------------------------------- #
# 请求 / 响应模型
# --------------------------------------------------------------------------- #
class ImageItem(BaseModel):
    """一张输入图片。role 用枚举，pydantic 自动对非法值返回 422 而非 500。"""
    url: str = Field(..., description="图片 URL")
    role: ImageRole = Field(
        ImageRole.REFERENCE_IMAGE,
        description="图片角色：first_frame(首帧) / last_frame(尾帧) / reference_image(参考图)",
    )


class CreateVideoRequest(BaseModel):
    model: str = Field(..., examples=["doubao-seedance-2-0-fast"])
    prompt: str = Field(..., examples=["一个女孩在樱花树下奔跑，电影感镜头"])
    images: list[ImageItem] | None = Field(
        None,
        description="输入图片列表。空=文生视频；1张首帧=首帧图生视频；"
                    "首帧+尾帧=首尾帧；多张参考图=多参考图模式",
    )
    seed: int | None = None
    extra_params: dict[str, Any] | None = Field(None, description="透传给方舟的其它参数")


class TaskIdResponse(BaseModel):
    id: str
    status: str = "queued"


class VideoStatusResponse(BaseModel):
    """查询任务状态的响应模型，让 OpenAPI schema 完整、前端可据此生成客户端。"""
    id: str
    status: str
    video_url: str | None = None
    cover_url: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# 路由：方舟原生异步风格
# --------------------------------------------------------------------------- #
def _to_image_inputs(items: list[ImageItem] | None) -> list[ImageInput] | None:
    """把 Pydantic 模型转成客户端用的 ImageInput。"""
    if not items:
        return None
    return [ImageInput(url=it.url, role=it.role) for it in items]


@app.post("/v1/videos", response_model=TaskIdResponse)
async def create_video(req: CreateVideoRequest) -> TaskIdResponse:
    try:
        task_id = await client().create_task(
            model=req.model,
            prompt=req.prompt,
            images=_to_image_inputs(req.images),
            seed=req.seed,
            extra_params=req.extra_params,
        )
    except VolcError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return TaskIdResponse(id=task_id)


@app.get("/v1/videos/{task_id}", response_model=VideoStatusResponse)
async def get_video(task_id: str) -> VideoStatusResponse:
    try:
        result = await client().get_task(task_id)
    except VolcError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return VideoStatusResponse(
        id=result.task_id,
        status=result.status,
        video_url=result.video_url,
        cover_url=result.cover_url,
        error=result.error,
    )


# --------------------------------------------------------------------------- #
# 路由：同步阻塞风格（提交并等待）
# --------------------------------------------------------------------------- #
@app.post("/v1/videos/sync")
async def create_video_sync(req: CreateVideoRequest) -> dict[str, Any]:
    try:
        result = await client().create_and_wait(
            model=req.model,
            prompt=req.prompt,
            images=_to_image_inputs(req.images),
            seed=req.seed,
            extra_params=req.extra_params,
        )
    except VolcError as e:
        raise HTTPException(status_code=504, detail=str(e))
    return {
        "id": result.task_id,
        "status": result.status,
        "video_url": result.video_url,
        "cover_url": result.cover_url,
        "error": result.error,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    # 仅返回存活状态，不暴露 api_key 是否配置（避免给未授权方探测面）
    return {"status": "ok"}
