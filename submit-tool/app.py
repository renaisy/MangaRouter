"""分镜批量提交小工具（Streamlit）—— v0.2

v0.2 新增：
  · 首尾帧 / 多参考图上传（适配 Seedance content 数组 + role）
  · 图片自动预上传到 MinIO 拿 URL 再提交
  · 可选「ComfyUI 专业模式」：触发内部专家预制的工作流模板
"""
from __future__ import annotations

import os
from datetime import datetime

import httpx
import streamlit as st
from minio import Minio

from comfyui_bridge import ComfyUIBridge, ComfyUIError, fill_template

# --------------------------------------------------------------------------- #
# 配置（从环境变量读取，便于容器化与安全）
# --------------------------------------------------------------------------- #
NEWAPI_BASE_URL = os.environ.get("SUBMIT_NEWAPI_BASE_URL", "http://localhost:13000").rstrip("/")
NEWAPI_TOKEN = os.environ.get("SUBMIT_NEWAPI_TOKEN", "")

NOCODB_BASE_URL = os.environ.get("NOCODB_BASE_URL", "http://localhost:18080").rstrip("/")
NOCODB_TOKEN = os.environ.get("NOCODB_TOKEN", "")

MINIO_ENDPOINT = os.environ.get("SUBMIT_MINIO_ENDPOINT", "localhost:19000")
MINIO_ACCESS_KEY = os.environ.get("SUBMIT_MINIO_ACCESS_KEY", "seedance-admin")
MINIO_SECRET_KEY = os.environ.get("SUBMIT_MINIO_SECRET_KEY", "")
MINIO_SECURE = os.environ.get("SUBMIT_MINIO_SECURE", "false").lower() == "true"

COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://localhost:8188").rstrip("/")

PRIORITY_TO_GROUP = {
    "草稿": "draft", "日常": "standard", "成片": "final",
    "draft": "draft", "standard": "standard", "final": "final",
}


# --------------------------------------------------------------------------- #
# 页面配置
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Seedance 分镜提交", page_icon="🎬", layout="wide")
st.title("🎬 Seedance 分镜提交工具")
st.caption("支持文生视频 / 首帧 / **首尾帧** / **多参考图** · v0.2")

mode = st.sidebar.radio(
    "选择模式",
    ["📝 标准提交（走 New-API 路由）", "🔧 ComfyUI 专业模式（触发预制工作流）"],
    index=0,
)

# --------------------------------------------------------------------------- #
# 侧边栏：连接配置
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.divider()
    st.subheader("连接配置")
    cfg = st.session_state
    cfg.setdefault("base", NEWAPI_BASE_URL)
    cfg.setdefault("token", NEWAPI_TOKEN)
    cfg.base = st.text_input("New-API 地址", value=cfg.base)
    cfg.token = st.text_input("New-API 令牌", value=cfg.token, type="password")

    cfg.nocodb_base = st.text_input("NocoDB 地址", value=NOCODB_BASE_URL)
    cfg.nocodb_token = st.text_input("NocoDB Token", value=NOCODB_TOKEN, type="password")

    cfg.minio_endpoint = st.text_input("MinIO 地址", value=MINIO_ENDPOINT)
    cfg.minio_ak = st.text_input("MinIO AccessKey", value=MINIO_ACCESS_KEY)
    cfg.minio_sk = st.text_input("MinIO SecretKey", value=MINIO_SECRET_KEY, type="password")

    cfg.comfyui_base = st.text_input("ComfyUI 地址（专业模式用）", value=COMFYUI_BASE_URL)


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def minio_client() -> Minio:
    return Minio(cfg.minio_endpoint, access_key=cfg.minio_ak,
                 secret_key=cfg.minio_sk, secure=MINIO_SECURE)


# 允许的图片后缀白名单（防伪造后缀/路径穿越）
_ALLOWED_IMG_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMG_BYTES = 20 * 1024 * 1024  # 20MB 上限


def upload_image_to_minio(uploaded_file, bucket: str = "storyboards") -> str:
    """把 Streamlit 上传的文件存进 MinIO，返回可访问 URL。

    安全加固（P2-1）：
      - 用 uuid 重命名，不信任客户端文件名（防路径穿越/对象名注入）
      - 校验后缀在白名单内
      - 限制大小（默认 20MB）
    """
    import io
    import uuid
    raw_name = str(getattr(uploaded_file, "name", ""))
    suffix = os.path.splitext(raw_name)[1].lower()
    if suffix not in _ALLOWED_IMG_SUFFIXES:
        raise ValueError(f"不支持的图片格式 {suffix or '(无后缀)'}，仅支持 {sorted(_ALLOWED_IMG_SUFFIXES)}")
    data = uploaded_file.getvalue()
    if len(data) > _MAX_IMG_BYTES:
        raise ValueError(f"图片过大（{len(data)/1024/1024:.1f}MB），上限 {_MAX_IMG_BYTES/1024/1024:.0f}MB")
    # uuid 重命名，保留合法后缀，杜绝文件名注入
    object_name = f"uploads/{datetime.now():%Y%m%d}/{uuid.uuid4().hex}{suffix}"
    client = minio_client()
    client.put_object(bucket, object_name, io.BytesIO(data),
                      length=len(data), content_type=uploaded_file.type or "image/png")
    # 内网直链（MinIO 桶需设为可读，或用预签名）
    return f"http://{cfg.minio_endpoint}/{bucket}/{object_name}"


def submit_via_newapi(model: str, prompt: str,
                      images: list[dict] | None, group: str) -> dict:
    """走 New-API（→ 适配器）提交，返回 {video_url, status, error}。"""
    headers = {"Authorization": f"Bearer {cfg.token}"}
    payload: dict = {"model": model, "prompt": prompt, "images": images}
    payload["extra_params"] = {"group": group}
    adapter_url = os.environ.get("ADAPTER_URL", "").rstrip()
    target = adapter_url if adapter_url else cfg.base.rstrip("/")
    url = f"{target}/v1/videos/sync"
    r = httpx.post(url, headers=headers, json=payload, timeout=900)
    if r.status_code >= 400:
        return {"status": "failed", "error": f"HTTP {r.status_code}: {r.text}", "video_url": None}
    return r.json()


def default_model_for(priority: str) -> str:
    group = PRIORITY_TO_GROUP.get(priority, "standard")
    return {"draft": "doubao-seedance-2-0-mini",
            "standard": "doubao-seedance-2-0-fast",
            "final": "doubao-seedance-2-0"}.get(group, "doubao-seedance-2-0-fast")


# --------------------------------------------------------------------------- #
# 标准提交模式
# --------------------------------------------------------------------------- #
if mode.startswith("📝"):
    st.header("标准提交（文生视频 / 首帧 / 首尾帧 / 多参考图）")

    prompt = st.text_area("提示词 Prompt *", height=100,
                          placeholder="例：特写，少女抬头望向夜空，樱花飘落，电影感慢动作")

    st.subheader("输入图片（可选）")
    st.caption("· 不传图 = 文生视频　· 只传首帧 = 首帧图生视频　"
               "· 传首帧+尾帧 = 首尾帧　· 传多张参考图 = 多参考图模式")

    col1, col2 = st.columns(2)
    with col1:
        first_frame = st.file_uploader("首帧图 (first_frame)", type=["png", "jpg", "jpeg", "webp"])
    with col2:
        last_frame = st.file_uploader("尾帧图 (last_frame)", type=["png", "jpg", "jpeg", "webp"])
    refs = st.file_uploader("参考图（可多选，role=reference_image）",
                            type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

    col_a, col_b = st.columns(2)
    with col_a:
        priority = st.selectbox("重要级（决定路由到哪档渠道）", ["草稿", "日常", "成片"], index=1)
    with col_b:
        model = st.text_input("指定模型（留空按重要级默认）", value="")

    if st.button("🚀 提交生成", type="primary"):
        if not prompt:
            st.error("请填写提示词")
            st.stop()
        if not cfg.token:
            st.error("请先在侧边栏填 New-API 令牌")
            st.stop()

        # 收集图片：先上传 MinIO 拿 URL
        images_payload: list[dict] = []
        with st.status("处理输入图片…", expanded=True) as status:
            try:
                if first_frame:
                    url = upload_image_to_minio(first_frame)
                    images_payload.append({"url": url, "role": "first_frame"})
                    st.write(f"✅ 首帧已上传：{url}")
                if last_frame:
                    url = upload_image_to_minio(last_frame)
                    images_payload.append({"url": url, "role": "last_frame"})
                    st.write(f"✅ 尾帧已上传：{url}")
                for ref in (refs or []):
                    url = upload_image_to_minio(ref)
                    images_payload.append({"url": url, "role": "reference_image"})
                    st.write(f"✅ 参考图已上传：{url}")
                status.update(label=f"共 {len(images_payload)} 张图已就绪", state="complete")
            except Exception as e:
                status.update(label=f"图片上传失败：{e}", state="error")
                st.stop()

        # 模式判定基于 role 组合，而非图片数量（避免 1 张参考图被误判为首帧）
        roles = {img["role"] for img in images_payload}
        if not images_payload:
            mode_desc = "文生视频"
        elif roles == {"first_frame", "last_frame"}:
            mode_desc = "首尾帧"
        elif "first_frame" in roles and "last_frame" not in roles and len(images_payload) == 1:
            mode_desc = "首帧"
        else:
            mode_desc = "多参考图" + ("（含首尾帧）" if roles >= {"first_frame", "last_frame"} else "")
        st.info(f"模式：{mode_desc}　路由分组：{PRIORITY_TO_GROUP[priority]}")

        with st.spinner("生成中（约 1-3 分钟，请勿关闭页面）…"):
            use_model = model or default_model_for(priority)
            res = submit_via_newapi(use_model, prompt,
                                    images_payload or None,
                                    PRIORITY_TO_GROUP[priority])
        if res.get("video_url"):
            st.success("✅ 生成成功！")
            st.video(res["video_url"])
            # 注意：成片链接来自方舟，有时效（通常几小时～1天），需及时下载保存
            st.caption(f"成片链接（方舟直链，有时效请及时下载保存）：{res['video_url']}")
        else:
            st.error(f"❌ 生成失败：{res.get('error')}")


# --------------------------------------------------------------------------- #
# ComfyUI 专业模式
# --------------------------------------------------------------------------- #
else:
    st.header("ComfyUI 专业模式")
    st.caption("触发内部专家预制的工作流模板。普通成员无需懂节点连线，填参数即可。")

    # 列出可用模板
    tpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = [f for f in os.listdir(tpl_dir) if f.endswith(".json")] if os.path.isdir(tpl_dir) else []
    if not templates:
        st.warning("未找到工作流模板。请把专家导出的 API 格式 JSON 放到 `submit-tool/templates/` 目录。")
        st.stop()

    chosen_tpl = st.selectbox("选择工作流模板", templates)

    # 读取模板，扫描其中的占位变量 {{xxx}}
    import json, re
    tpl_path = os.path.join(tpl_dir, chosen_tpl)
    with open(tpl_path, encoding="utf-8") as f:
        template = json.load(f)
    tpl_text = json.dumps(template)
    placeholders = sorted(set(re.findall(r"\{\{(\w+)\}\}", tpl_text)))

    st.subheader("填写参数")
    variables: dict[str, object] = {}
    for ph in placeholders:
        # 约定：以 _img 结尾的是图片，用上传；含 list 的是多值；其余文本
        if ph.endswith("_img") or ph.endswith("_image"):
            variables[ph] = st.file_uploader(f"{{{{{ph}}}}}（图片）", key=ph,
                                             type=["png", "jpg", "jpeg", "webp"])
        elif "list" in ph or "refs" in ph:
            variables[ph] = st.file_uploader(f"{{{{{ph}}}}}（多图）", key=ph,
                                             accept_multiple_files=True,
                                             type=["png", "jpg", "jpeg", "webp"])
        else:
            variables[ph] = st.text_input(f"{{{{{ph}}}}}", key=ph)

    if st.button("🚀 提交到 ComfyUI", type="primary"):
        if not cfg.comfyui_base:
            st.error("请先在侧边栏填 ComfyUI 地址")
            st.stop()

        with st.status("准备参数…", expanded=True) as status:
            # 上传图片类变量到 ComfyUI 的 input 目录（通过 /upload/image）
            bridge = ComfyUIBridge(cfg.comfyui_base)
            try:
                if not bridge.health():
                    raise ComfyUIError(f"ComfyUI 不可达：{cfg.comfyui_base}")
                # 把文件型变量转成 ComfyUI 可识别的文件名
                final_vars: dict[str, object] = {}
                for k, v in variables.items():
                    if v is None:
                        final_vars[k] = ""
                    elif isinstance(v, list):
                        # 多图：上传每张，返回文件名列表
                        names = [_upload_to_comfyui(bridge, f) for f in v]
                        final_vars[k] = names
                    elif hasattr(v, "getvalue"):  # 单文件
                        final_vars[k] = _upload_to_comfyui(bridge, v)
                    else:
                        final_vars[k] = v
                status.update(label="参数就绪，提交工作流…")

                workflow = fill_template(template, final_vars)
                prompt_id = bridge.submit(workflow)
                st.write(f"已提交，prompt_id = `{prompt_id}`")
                status.update(label="等待生成完成…")

                entry = bridge.wait_result(prompt_id)
                urls = bridge.output_urls(entry)
                status.update(label="生成完成", state="complete")

                if urls:
                    st.success(f"✅ 完成，{len(urls)} 个输出")
                    for u in urls:
                        st.video(u) if u.endswith((".mp4", ".webm", ".gif")) else st.image(u)
                        st.caption(u)
                else:
                    st.warning("工作流完成但未找到输出文件，请到 ComfyUI 界面查看。")
            except ComfyUIError as e:
                status.update(label=f"失败：{e}", state="error")
            finally:
                bridge.close()


def _upload_to_comfyui(bridge: ComfyUIBridge, uploaded) -> str:
    """把 Streamlit 文件上传到 ComfyUI 的 input 目录，返回上传后的文件名。"""
    r = bridge._client.post(
        f"{bridge.base_url}/upload/image",
        files={"image": (uploaded.name, uploaded.getvalue(), uploaded.type or "image/png")},
        data={"overwrite": "true"},
    )
    r.raise_for_status()
    return r.json().get("name", uploaded.name)
