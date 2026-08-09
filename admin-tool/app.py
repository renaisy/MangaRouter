"""MangaRouter 管理员配置页 —— New-API 渠道 / 令牌薄封装。

安全：ADMIN_* 仅环境变量；页面不预填、不可改 Token。
公网须经 Caddy basicauth（admin 用户，与 team 分离）。
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from newapi_admin import (
    CHANNEL_STATUS_ENABLED,
    CHANNEL_STATUS_MANUAL_DISABLED,
    CHANNEL_TYPE_CUSTOM,
    CHANNEL_TYPE_OPENAI,
    CHANNEL_TYPE_VOLCENGINE,
    ChannelDraft,
    NewAPIAdmin,
    redact_key,
    validate_group,
)
from templates_presets import CHANNEL_TYPE_LABELS, manga_triple_presets

st.set_page_config(page_title="MangaRouter 管理", page_icon="⚙️", layout="wide")
st.title("⚙️ MangaRouter 渠道管理")
st.caption("薄封装 New-API · 密钥只存 New-API · 需 Caddy basicauth")

admin = NewAPIAdmin()

with st.sidebar:
    st.header("连接状态（只读）")
    st.text(f"New-API: {admin.base_url}")
    st.text(f"User ID: {admin.user_id or '(未配置)'}")
    st.text(f"Access Token: {'已配置' if admin.access_token else '未配置'}")
    st.divider()
    page = st.radio(
        "功能",
        ["渠道一览", "添加渠道", "模板向导", "令牌管理"],
        index=0,
    )

if not admin.is_configured():
    st.error(
        "请在服务器 `.env` 配置 `ADMIN_NEWAPI_TOKEN`（系统管理 access_token）"
        "与 `ADMIN_NEWAPI_USER_ID`（与 token 所属用户 ID 一致，root 通常为 1）。"
        "在 New-API 个人设置中生成「系统访问令牌 / access token」。"
    )
    st.stop()


def _safe_channels() -> list[dict]:
    try:
        return admin.list_channels()
    except Exception as e:
        st.error(f"拉取渠道失败：{e}")
        return []


# --------------------------------------------------------------------------- #
# 渠道一览
# --------------------------------------------------------------------------- #
if page == "渠道一览":
    st.subheader("渠道列表")
    if st.button("🔄 刷新"):
        st.rerun()
    rows = _safe_channels()
    if not rows:
        st.info("暂无渠道，或拉取失败。可用「模板向导」一键创建。")
    else:
        view = []
        for c in rows:
            view.append({
                "ID": c.get("id"),
                "名称": c.get("name"),
                "类型": c.get("type"),
                "分组": c.get("group"),
                "模型": (c.get("models") or "")[:60],
                "权重": c.get("weight"),
                "优先级": c.get("priority"),
                "状态": c.get("status"),
                "BaseURL": c.get("base_url") or "",
            })
        st.dataframe(pd.DataFrame(view), use_container_width=True, hide_index=True)

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            cid = st.number_input("渠道 ID", min_value=1, step=1, value=int(rows[0].get("id") or 1))
        with col2:
            action = st.selectbox("操作", ["测试连通", "启用", "禁用", "删除"])
        with col3:
            confirm_name = st.text_input("删除时请输入渠道名称确认", value="")

        if st.button("执行", type="primary"):
            try:
                if action == "测试连通":
                    res = admin.test_channel(int(cid))
                    st.success(f"测试返回：{res}")
                elif action in ("启用", "禁用"):
                    full = admin.get_channel(int(cid))
                    if not full:
                        raise RuntimeError("未找到渠道详情（可能列表省略了 key）")
                    admin.set_channel_status(full, enabled=(action == "启用"))
                    st.success(f"已{action}渠道 {cid}")
                elif action == "删除":
                    full = admin.get_channel(int(cid))
                    name = (full or {}).get("name") or ""
                    if confirm_name != name:
                        st.error(f"确认名不匹配（期望「{name}」）")
                    else:
                        admin.delete_channel(int(cid))
                        st.success(f"已删除渠道 {cid}")
                        st.rerun()
            except Exception as e:
                st.error(str(e))

# --------------------------------------------------------------------------- #
# 添加渠道
# --------------------------------------------------------------------------- #
elif page == "添加渠道":
    st.subheader("添加 / 更新渠道")
    edit_id = st.number_input("更新时填写渠道 ID（新建填 0）", min_value=0, step=1, value=0)
    name = st.text_input("渠道名称 *", value="")
    type_label = st.selectbox(
        "类型",
        options=list(CHANNEL_TYPE_LABELS.values()) + ["其它(自定义数字)"],
        index=0,
    )
    type_map = {v: k for k, v in CHANNEL_TYPE_LABELS.items()}
    if type_label == "其它(自定义数字)":
        ch_type = st.number_input("type 数字", min_value=0, value=CHANNEL_TYPE_CUSTOM)
    else:
        ch_type = type_map[type_label]

    key = st.text_input("上游 API Key *", type="password", help="不会回显到环境；仅提交到 New-API")
    base_url = st.text_input("Base URL", value="http://seedance-adapter:18008",
                             help="走适配器填 http://seedance-adapter:18008")
    models = st.text_input("模型（逗号分隔）*", value="doubao-seedance-2-0-fast")
    group = st.selectbox("分组", ["draft", "standard", "final", "default", "自定义"])
    if group == "自定义":
        group = st.text_input("自定义分组名", value="")
        st.warning("submit-tool 默认只路由 draft/standard/final")
    wcol, pcol = st.columns(2)
    with wcol:
        weight = st.number_input("权重", min_value=0, value=100)
    with pcol:
        priority = st.number_input("优先级（数字越小越优先）", min_value=0, value=1)

    if st.button("保存到 New-API", type="primary"):
        try:
            if not name or not key or not models:
                raise ValueError("名称、Key、模型为必填")
            validate_group(group, allow_custom=True)
            draft = ChannelDraft(
                name=name,
                type=int(ch_type),
                key=key,
                models=models,
                group=group,
                base_url=base_url,
                weight=int(weight),
                priority=int(priority),
                id=int(edit_id) if edit_id else None,
            )
            if edit_id:
                admin.update_channel(draft)
                st.success(f"已更新渠道 id={edit_id}")
            else:
                admin.add_channel(draft)
                st.success("已创建渠道")
        except Exception as e:
            st.error(str(e))

# --------------------------------------------------------------------------- #
# 模板向导
# --------------------------------------------------------------------------- #
elif page == "模板向导":
    st.subheader("一键创建漫剧三档渠道")
    st.markdown(
        "按文档推荐创建 **draft / standard / final** 渠道。"
        "若 New-API 不原生支持 Seedance 异步，请勾选「经 seedance-adapter」。"
    )
    use_adapter = st.checkbox("经 seedance-adapter（推荐）", value=True)
    volc_key = st.text_input(
        "渠道上游 Key *",
        type="password",
        help="走适配器时填 ADAPTER_API_TOKEN；直连方舟时填火山 API Key",
    )
    with st.expander("可选：聚合渠道兜底（draft）"):
        agg_key = st.text_input("聚合 API Key", type="password")
        agg_base = st.text_input("聚合 Base URL", value="")
        agg_models = st.text_input("聚合模型列表", value="")

    if st.button("创建预设渠道", type="primary"):
        if not volc_key:
            st.error("请填写上游 Key")
            st.stop()
        drafts = manga_triple_presets(
            volc_api_key=volc_key,
            use_adapter=use_adapter,
            aggregator_api_key=agg_key,
            aggregator_base_url=agg_base,
            aggregator_models=agg_models,
        )
        ok, fail = 0, 0
        for d in drafts:
            try:
                admin.add_channel(d)
                st.write(f"✅ {d.name} → group={d.group}")
                ok += 1
            except Exception as e:
                st.write(f"❌ {d.name}: {e}")
                fail += 1
        st.success(f"完成：成功 {ok}，失败 {fail}")

# --------------------------------------------------------------------------- #
# 令牌
# --------------------------------------------------------------------------- #
else:
    st.subheader("令牌管理")
    st.caption("令牌 API 使用同一 access token；列表不展示完整 key。")
    if st.button("🔄 刷新令牌列表"):
        st.rerun()
    try:
        tokens = admin.list_tokens()
    except Exception as e:
        st.error(f"拉取令牌失败：{e}")
        tokens = []

    if tokens:
        tv = []
        for t in tokens:
            tv.append({
                "ID": t.get("id"),
                "名称": t.get("name"),
                "分组": t.get("group"),
                "额度": t.get("remain_quota"),
                "无限额": t.get("unlimited_quota"),
                "Key": redact_key(t.get("key")),
                "状态": t.get("status"),
            })
        st.dataframe(pd.DataFrame(tv), use_container_width=True, hide_index=True)
    else:
        st.info("暂无令牌")

    st.divider()
    st.markdown("#### 新建令牌")
    tname = st.text_input("令牌名称", value="全员-提交")
    tgroup = st.text_input("允许分组", value="draft,standard,final")
    unlimited = st.checkbox("无限额度", value=False)
    yuan = st.number_input("额度（元，按 1元=500000 配额估算）", min_value=0, value=500)
    if st.button("创建令牌", type="primary"):
        try:
            remain = 0 if unlimited else int(yuan * 500_000)
            res = admin.add_token(
                tname,
                group=tgroup,
                remain_quota=remain,
                unlimited_quota=unlimited,
            )
            st.success("已创建。请到 New-API 后台复制完整令牌（若下方未显示明文）。")
            key = (res or {}).get("key") if isinstance(res, dict) else None
            if key:
                st.code(key)
                st.warning("请立即保存；刷新后不再完整显示。")
            else:
                st.json(res)
        except Exception as e:
            st.error(str(e))

    st.divider()
    del_id = st.number_input("删除令牌 ID", min_value=1, step=1, value=1)
    if st.button("删除令牌"):
        try:
            admin.delete_token(int(del_id))
            st.success(f"已删除令牌 {del_id}")
        except Exception as e:
            st.error(str(e))
