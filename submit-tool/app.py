"""分镜提交工具（Streamlit）—— VPS 部署版

安全约定（对抗审查 C1/C3）：
  · 密钥与 Base URL 仅来自环境变量，UI 不可编辑、不预填到浏览器
  · 公网须经 Caddy basicauth（见 deploy/Caddyfile）
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import streamlit as st

from comfyui_bridge import ComfyUIBridge, ComfyUIError, fill_template
from minio_store import (
    archive_trusted_media_url,
    project_object_prefix,
    upload_streamlit_file,
    validate_image_url_for_submit,
)
from newapi_submit import (
    default_model_for,
    group_for_priority,
    submit_async,
    token_for_group,
)
from nocodb_client import NocoDBStoryboards
from submit_cache import cache_enabled, find_cached_success, submit_fingerprint


@dataclass(frozen=True)
class AppConfig:
    newapi_base: str
    newapi_token: str
    nocodb_base: str
    nocodb_token: str
    table_id: str
    comfyui_base: str


def load_config() -> AppConfig:
    return AppConfig(
        newapi_base=os.environ.get("SUBMIT_NEWAPI_BASE_URL", "http://new-api:3000").rstrip("/"),
        newapi_token=os.environ.get("SUBMIT_NEWAPI_TOKEN", ""),
        nocodb_base=os.environ.get("NOCODB_BASE_URL", "http://nocodb:8080").rstrip("/"),
        nocodb_token=os.environ.get("NOCODB_TOKEN", ""),
        table_id=os.environ.get("STORYBOARDS_TABLE_ID", ""),
        comfyui_base=os.environ.get("COMFYUI_BASE_URL", "").rstrip("/"),
    )


CFG = load_config()


def _upload_to_comfyui(bridge: ComfyUIBridge, uploaded) -> str:
    """上传到 ComfyUI input，使用 uuid 文件名避免覆盖。"""
    suffix = os.path.splitext(str(getattr(uploaded, "name", "")) or ".png")[1] or ".png"
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    r = bridge._client.post(
        f"{bridge.base_url}/upload/image",
        files={"image": (safe_name, uploaded.getvalue(), uploaded.type or "image/png")},
        data={"overwrite": "true"},
    )
    r.raise_for_status()
    return r.json().get("name", safe_name)


def _comfyui_host_allowed(base: str) -> bool:
    """仅允许环境变量配置的 ComfyUI Host（防 SSRF）。"""
    if not CFG.comfyui_base:
        return False
    return urlparse(base).netloc == urlparse(CFG.comfyui_base).netloc


st.set_page_config(page_title="Seedance 分镜提交", page_icon="🎬", layout="wide")
st.title("🎬 Seedance 分镜提交工具")
st.caption("异步提交 · NocoDB 批量 · 公网预签名图传 · 多剧 ProjectKey · VPS 部署")

mode = st.sidebar.radio(
    "选择模式",
    [
        "📝 标准提交（单条）",
        "📋 NocoDB 批量提交",
        "🔧 ComfyUI 专业模式",
    ],
    index=0,
)

with st.sidebar:
    st.divider()
    st.caption("连接信息来自服务器环境变量（不可在页面修改）。")
    st.text(f"New-API: {CFG.newapi_base}")
    st.text(f"NocoDB: {CFG.nocodb_base}")
    st.text(f"表 ID: {CFG.table_id or '(未配置)'}")
    st.text(f"令牌: {'已配置' if CFG.newapi_token else '未配置'}")
    if CFG.comfyui_base:
        st.text(f"ComfyUI: {CFG.comfyui_base}")
    st.caption("成片档请使用仅绑定 final 分组的令牌（SUBMIT_TOKEN_FINAL）。")


def _images_from_uploaders(first_frame, last_frame, refs, project_key: str) -> list[dict]:
    images: list[dict] = []
    if first_frame:
        images.append({
            "url": upload_streamlit_file(first_frame, project_key=project_key),
            "role": "first_frame",
        })
    if last_frame:
        images.append({
            "url": upload_streamlit_file(last_frame, project_key=project_key),
            "role": "last_frame",
        })
    for ref in (refs or []):
        images.append({
            "url": upload_streamlit_file(ref, project_key=project_key),
            "role": "reference_image",
        })
    return images


def _try_cache_hit(prompt: str, priority: str, model: str, images: list[dict] | None,
                   project_key: str) -> dict | None:
    if not cache_enabled():
        return None
    urls = [str(i.get("url") or "") for i in (images or [])]
    fp = submit_fingerprint(
        prompt, model=model or default_model_for(priority), priority=priority,
        image_urls=urls, project_key=project_key,
    )
    nc = NocoDBStoryboards(CFG.nocodb_base, CFG.nocodb_token, CFG.table_id)
    try:
        if not nc.is_configured():
            return None
        hit = find_cached_success(nc, fp)
        if hit:
            return {"fingerprint": fp, "row": hit}
        return {"fingerprint": fp, "row": None}
    finally:
        nc.close()


def _enqueue(prompt: str, priority: str, model: str, images: list[dict] | None,
             extra_fields: dict | None = None, project_key: str = "default") -> str:
    """异步提交并写入 NocoDB running；返回 task_id。缓存命中则返回 cached:<id>。"""
    use_model = model or default_model_for(priority)
    cache_info = _try_cache_hit(prompt, priority, use_model, images, project_key)
    fingerprint = (cache_info or {}).get("fingerprint") or ""
    hit_row = (cache_info or {}).get("row")
    if hit_row:
        share = hit_row.get("ShareUrl") or hit_row.get("VideoUrl") or ""
        st.info(f"缓存命中，复用成片：{share}")
        return f"cached:{hit_row.get('Id') or hit_row.get('id')}"

    group = group_for_priority(priority)
    token = token_for_group(group, CFG.newapi_token)
    if not token:
        raise RuntimeError("未配置 SUBMIT_NEWAPI_TOKEN / SUBMIT_TOKEN_*")
    res = submit_async(
        CFG.newapi_base, token,
        model=use_model, prompt=prompt, images=images or None, group=group,
    )
    if not res.get("id"):
        raise RuntimeError(res.get("error") or "未返回 task_id")
    task_id = str(res["id"])

    nc = NocoDBStoryboards(CFG.nocodb_base, CFG.nocodb_token, CFG.table_id)
    try:
        base_fields = {
            "Status": "running",
            "TaskId": task_id,
            "Prompt": prompt,
            "Priority": priority,
            "Model": use_model,
            "ProjectKey": project_key,
            "ErrorMsg": "",
            "SubmittedAt": datetime.now().isoformat(timespec="seconds"),
        }
        if fingerprint:
            base_fields["Fingerprint"] = fingerprint
        if nc.is_configured() and extra_fields and extra_fields.get("_record_id"):
            rid = extra_fields["_record_id"]
            nc.patch_record(rid, {
                **base_fields,
                **{k: v for k, v in (extra_fields or {}).items() if not k.startswith("_")},
            })
        elif nc.is_configured() and not (extra_fields or {}).get("_skip_create"):
            try:
                nc.create_record({
                    **base_fields,
                    **{k: v for k, v in (extra_fields or {}).items() if not k.startswith("_")},
                })
            except Exception as e:
                st.warning(f"已提交任务 {task_id}，但写入 NocoDB 失败：{e}（worker 无法自动回填）")
    finally:
        nc.close()
    return task_id


# --------------------------------------------------------------------------- #
# 标准单条
# --------------------------------------------------------------------------- #
if mode.startswith("📝"):
    st.header("标准提交（异步）")
    st.info("提交后立即返回 task_id；成片由后台 worker 归档。请勿长时间占用页面等待。")

    project_key = st.text_input("ProjectKey（剧目键）*", value="", help="多剧隔离必填，如 manga-a")
    prompt = st.text_area("提示词 Prompt *", height=100)
    col1, col2 = st.columns(2)
    with col1:
        first_frame = st.file_uploader("首帧图", type=["png", "jpg", "jpeg", "webp"])
    with col2:
        last_frame = st.file_uploader("尾帧图", type=["png", "jpg", "jpeg", "webp"])
    refs = st.file_uploader("参考图（可多选）", type=["png", "jpg", "jpeg", "webp"],
                            accept_multiple_files=True)
    col_a, col_b = st.columns(2)
    with col_a:
        priority = st.selectbox("重要级", ["草稿", "日常", "成片"], index=1)
    with col_b:
        model = st.text_input("指定模型（留空按重要级）", value="")

    if st.button("🚀 异步提交", type="primary"):
        if not project_key.strip():
            st.error("请填写 ProjectKey")
            st.stop()
        if not prompt:
            st.error("请填写提示词")
            st.stop()
        if not CFG.newapi_token and not token_for_group(group_for_priority(priority)):
            st.error("服务器未配置 New-API 令牌")
            st.stop()
        try:
            pk = project_key.strip()
            with st.status("上传图片并提交…") as status:
                images = _images_from_uploaders(first_frame, last_frame, refs, pk)
                status.update(label=f"图片 {len(images)} 张，提交任务…")
                tid = _enqueue(prompt, priority, model, images or None, project_key=pk)
                status.update(label=f"已入队 task_id={tid}", state="complete")
            st.success(f"已提交。task_id=`{tid}`。请到 NocoDB Storyboards 查看 Status。")
        except Exception as e:
            st.error(f"提交失败：{e}")

# --------------------------------------------------------------------------- #
# NocoDB 批量
# --------------------------------------------------------------------------- #
elif mode.startswith("📋"):
    st.header("NocoDB 批量提交")
    if not (CFG.nocodb_token and CFG.table_id):
        st.warning("请配置环境变量 NOCODB_TOKEN 与 STORYBOARDS_TABLE_ID。")
        st.stop()

    filter_pk = st.text_input("按 ProjectKey 过滤（必填）*", value="")
    if not filter_pk.strip():
        st.warning("请先填写 ProjectKey，避免跨剧误提交。")
        st.stop()

    nc = NocoDBStoryboards(CFG.nocodb_base, CFG.nocodb_token, CFG.table_id)
    try:
        if st.button("🔄 刷新 pending 分镜"):
            st.session_state["pending_rows"] = nc.list_by_status(
                "pending", project_key=filter_pk.strip(),
            )
        rows = st.session_state.get("pending_rows")
        if rows is None:
            rows = nc.list_by_status("pending", project_key=filter_pk.strip())
        st.session_state["pending_rows"] = rows
        if not rows:
            st.info(f"ProjectKey={filter_pk.strip()} 下没有 Status=pending 的分镜。")
            st.stop()

        labels = []
        for r in rows:
            rid = nc.record_id(r)
            labels.append(f"Id={rid} | {r.get('ShotNo') or '-'} | {(r.get('Prompt') or '')[:40]}")
        selected = st.multiselect("选择要提交的分镜", labels, default=labels)
        if st.button("🚀 批量异步提交所选", type="primary"):
            chosen = [rows[i] for i, lb in enumerate(labels) if lb in selected]
            ok, fail = 0, 0
            progress = st.progress(0.0)
            for i, row in enumerate(chosen):
                rid = nc.record_id(row)
                prompt = str(row.get("Prompt") or "").strip()
                if not prompt or not rid:
                    fail += 1
                    continue
                pk = str(row.get("ProjectKey") or filter_pk).strip() or filter_pk.strip()
                priority = str(row.get("Priority") or "日常")
                model = str(row.get("Model") or "")
                images = None
                img_url = str(row.get("ImageUrl") or "").strip()
                if img_url:
                    try:
                        validate_image_url_for_submit(img_url)
                        images = [{"url": img_url, "role": "first_frame"}]
                    except ValueError as e:
                        nc.patch_record(rid, {"Status": "failed", "ErrorMsg": str(e)[:500]})
                        st.write(f"❌ Id={rid}: {e}")
                        fail += 1
                        progress.progress((i + 1) / max(len(chosen), 1))
                        continue
                try:
                    tid = _enqueue(
                        prompt, priority, model, images,
                        project_key=pk,
                        extra_fields={
                            "_record_id": rid,
                            "Project": row.get("Project") or "",
                            "Episode": row.get("Episode") or "",
                            "ShotNo": row.get("ShotNo") or "",
                            "ProjectKey": pk,
                        },
                    )
                    st.write(f"✅ Id={rid} → task_id={tid}")
                    ok += 1
                except Exception as e:
                    nc.patch_record(rid, {"Status": "failed", "ErrorMsg": str(e)[:500]})
                    st.write(f"❌ Id={rid}: {e}")
                    fail += 1
                progress.progress((i + 1) / max(len(chosen), 1))
            st.success(f"完成：成功 {ok}，失败 {fail}。worker 将自动归档成片。")
            st.session_state["pending_rows"] = nc.list_by_status(
                "pending", project_key=filter_pk.strip(),
            )
    finally:
        nc.close()

# --------------------------------------------------------------------------- #
# ComfyUI
# --------------------------------------------------------------------------- #
else:
    st.header("ComfyUI 专业模式")
    st.caption(
        "仓库内 templates/*.json 默认为骨架；须专家用 ComfyUI「保存(API格式)」替换后才能生产。"
        "成功后会归档 MinIO 并写入 NocoDB。"
    )
    if not CFG.comfyui_base:
        st.warning("未配置 COMFYUI_BASE_URL")
        st.stop()
    project_key = st.text_input("ProjectKey（剧目键）*", value="", key="comfy_pk")
    tpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = [f for f in os.listdir(tpl_dir) if f.endswith(".json")] if os.path.isdir(tpl_dir) else []
    if not templates:
        st.warning("未找到 templates/*.json")
        st.stop()
    chosen_tpl = st.selectbox("工作流模板", templates)
    with open(os.path.join(tpl_dir, chosen_tpl), encoding="utf-8") as f:
        template = json.load(f)
    if template.get("_comment") or template.get("_how_to_use"):
        st.info("当前为骨架/含说明字段的模板；提交前会自动剥离 `_` 元数据键。")
    placeholders = sorted(set(re.findall(r"\{\{(\w+)\}\}", json.dumps(template))))
    variables: dict[str, object] = {}
    for ph in placeholders:
        if ph.endswith("_img") or ph.endswith("_image"):
            variables[ph] = st.file_uploader(f"{{{{{ph}}}}}", key=ph, type=["png", "jpg", "jpeg", "webp"])
        elif "list" in ph or "refs" in ph:
            variables[ph] = st.file_uploader(
                f"{{{{{ph}}}}}（多图）", key=ph, accept_multiple_files=True,
                type=["png", "jpg", "jpeg", "webp"],
            )
        else:
            variables[ph] = st.text_input(f"{{{{{ph}}}}}", key=ph)

    prompt_hint = str(variables.get("prompt") or "")
    if st.button("🚀 提交到 ComfyUI", type="primary"):
        if not project_key.strip():
            st.error("请填写 ProjectKey")
            st.stop()
        if not _comfyui_host_allowed(CFG.comfyui_base):
            st.error("ComfyUI 地址未在允许列表中")
            st.stop()
        pk = project_key.strip()
        bridge = ComfyUIBridge(CFG.comfyui_base)
        try:
            if not bridge.health():
                raise ComfyUIError(f"ComfyUI 不可达：{CFG.comfyui_base}")
            final_vars: dict[str, object] = {}
            for k, v in variables.items():
                if v is None:
                    final_vars[k] = ""
                elif isinstance(v, list):
                    final_vars[k] = [_upload_to_comfyui(bridge, f) for f in v]
                elif hasattr(v, "getvalue"):
                    final_vars[k] = _upload_to_comfyui(bridge, v)
                else:
                    final_vars[k] = v
            workflow = fill_template(template, final_vars)
            prompt_id = bridge.submit(workflow)
            st.write(f"prompt_id=`{prompt_id}`，轮询中…")
            entry = bridge.wait_result(prompt_id)
            urls = bridge.output_urls(entry)
            if not urls:
                st.warning("完成但未找到输出文件")
                st.stop()
            st.success(f"完成，{len(urls)} 个输出")
            for u in urls:
                lower = u.lower()
                if any(lower.endswith(ext) or f".{ext.split('.')[-1]}" in lower
                       for ext in (".mp4", ".webm", ".gif")):
                    st.video(u)
                else:
                    st.image(u)
            # 归档首个媒体到 MinIO + NocoDB
            first = urls[0]
            prefix = project_object_prefix(pk, "comfyui", prompt_id)
            try:
                minio_path, share = archive_trusted_media_url(
                    first, prefix, trusted_base_url=CFG.comfyui_base,
                )
                st.success(f"已归档：{minio_path}")
                st.code(share)
                nc = NocoDBStoryboards(CFG.nocodb_base, CFG.nocodb_token, CFG.table_id)
                try:
                    if nc.is_configured():
                        nc.create_record({
                            "Prompt": prompt_hint or f"comfyui:{chosen_tpl}",
                            "Priority": "日常",
                            "Model": "comfyui",
                            "Status": "succeeded",
                            "TaskId": prompt_id,
                            "VideoUrl": first,
                            "MinioPath": minio_path,
                            "ShareUrl": share,
                            "ProjectKey": pk,
                            "SubmittedAt": datetime.now().isoformat(timespec="seconds"),
                        })
                        st.info("已写入 NocoDB Storyboards")
                finally:
                    nc.close()
            except Exception as e:
                st.warning(f"预览成功但归档/回填失败：{e}")
        except ComfyUIError as e:
            st.error(str(e))
        finally:
            bridge.close()
