"""成本看板（Streamlit）—— 从 NocoDB Costs 表读数据做可视化。

回答制片/技术负责人的核心问题：
  · 总共花了多少？昨天/上周花了多少（环比）？
  · 谁花的最多？哪个渠道/模型最贵？
  · 草稿/日常/成片 三档占比如何？有没有人滥用成片档？
  · 各渠道成功率如何？（结合 New-API 日志，进阶）

启动：streamlit run app.py
或 Docker（见 Dockerfile），默认 18502 端口。
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pandas as pd
import streamlit as st

NOCODB_BASE_URL = os.environ.get("DASH_NOCODB_BASE_URL", "http://nocodb:8080").rstrip("/")
NOCODB_TOKEN = os.environ.get("DASH_NOCODB_TOKEN", "")
COSTS_TABLE_ID = os.environ.get("DASH_COSTS_TABLE_ID", "")
_MAX_PAGES = int(os.environ.get("DASH_MAX_PAGES", "200"))

import re
_TABLE_ID_RE = re.compile(r"^m[A-Za-z0-9_]+$")


def _valid_table_id(tid: str) -> bool:
    return bool(tid) and bool(_TABLE_ID_RE.match(tid))


st.set_page_config(page_title="Seedance 成本看板", page_icon="💰", layout="wide")
st.title("💰 Seedance 成本看板")


# --------------------------------------------------------------------------- #
# 侧边栏：仅展示只读连接状态（密钥不进浏览器）
# --------------------------------------------------------------------------- #
base = NOCODB_BASE_URL
token = NOCODB_TOKEN
table_id = COSTS_TABLE_ID

with st.sidebar:
    st.header("数据源（环境变量）")
    st.caption("地址与 Token 仅来自服务器环境，页面不可修改。公网请加 Caddy basicauth。")
    st.text(f"NocoDB: {base}")
    st.text(f"表 ID: {table_id or '(未配置)'}")
    st.text(f"Token: {'已配置' if token else '未配置'}")
    if table_id and not _valid_table_id(table_id):
        st.warning("表 ID 格式异常（期望类似 mt_xxxxx）")

    st.divider()
    st.subheader("筛选")
    today = date.today()
    default_start = today - timedelta(days=30)
    date_range = st.date_input("日期范围", value=(default_start, today),
                               max_value=today)
    project_filter = st.text_input("按 Project 过滤（空=全部）", value="")


@st.cache_data(ttl=300)
def fetch_costs(base: str, token: str, table_id: str) -> pd.DataFrame:
    """从 NocoDB Costs 表拉全量记录，返回 DataFrame。

    注意：参数不要加下划线前缀（_base/_token/_table_id）——Streamlit 的 cache_data
    约定 _ 开头的参数不参与缓存键，会导致用户改了地址/token 后看板不刷新。
    """
    if not (token and table_id):
        return pd.DataFrame()
    if not _valid_table_id(table_id):
        raise RuntimeError(f"非法 Costs 表 ID：{table_id}")
    headers = {"xc-token": token}
    all_rows: list[dict] = []
    offset = 0
    page = 0
    while True:
        page += 1
        if page > _MAX_PAGES:
            break
        url = f"{base}/api/v2/tables/{table_id}/records"
        try:
            r = httpx.get(url, headers=headers, params={"limit": 100, "offset": offset}, timeout=30)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # 401/404 等：友好提示而非整页 traceback
            raise RuntimeError(f"NocoDB 请求失败 HTTP {e.response.status_code}：请检查 Token 和表 ID") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"无法连接 NocoDB（{base}）：{e}") from e
        data = r.json() or {}
        rows = data.get("list") or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        offset += 100
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    # 字段规整（NocoDB 列名与 init_schema 一致）
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ("Amount", "Calls", "Tokens"):
        if col in df.columns:
            # 保留 NaN，不强制填 0，避免拉低均值；聚合时 skipna
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def safe_filter(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty:
        return df
    if "Date" not in df.columns:
        st.warning("Costs 表缺少 Date 列，无法按日期筛选")
        return df.iloc[0:0].copy()
    mask = (df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)
    return df[mask].copy()


# --------------------------------------------------------------------------- #
# 拉数据
# --------------------------------------------------------------------------- #
try:
    df_all = fetch_costs(base, token, table_id)
except RuntimeError as e:
    st.error(f"读取成本数据失败：{e}")
    st.stop()

if df_all.empty:
    st.warning("未读到数据。请先：①在侧边栏填好 NocoDB Token 和 Costs 表 ID；"
               "②确认 cost-sync 已跑过（docs/第三方渠道接入实例.md 末尾）。")
    st.stop()

# 处理 date_range（Streamlit 可能返回单个 date 或元组）
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
else:
    start = end = date_range

df = safe_filter(df_all, start, end)
if project_filter.strip() and "Project" in df.columns:
    df = df[df["Project"].astype(str) == project_filter.strip()].copy()
if df.empty:
    st.warning(f"{start} ~ {end} 无数据")
    st.stop()

st.caption(f"数据范围：{start} ~ {end}　共 {len(df)} 条汇总记录")

# --------------------------------------------------------------------------- #
# 顶部 KPI
# --------------------------------------------------------------------------- #
total = df["Amount"].sum()
total_calls = int(df["Calls"].sum()) if "Calls" in df.columns else 0
total_tokens = int(df["Tokens"].sum()) if "Tokens" in df.columns else 0

# 计算环比：与等长的上一周期比
period_days = (end - start).days + 1
prev_end = start - timedelta(days=1)
prev_start = prev_end - timedelta(days=period_days - 1)
df_prev = safe_filter(df_all, prev_start, prev_end)
prev_total = df_prev["Amount"].sum() if not df_prev.empty else 0
ratio = ((total - prev_total) / prev_total * 100) if prev_total > 0 else None

k1, k2, k3, k4 = st.columns(4)
k1.metric("总花费 (元)", f"¥{total:,.2f}",
          f"{ratio:+.1f}% vs 上期" if ratio is not None else "无上期数据")
k2.metric("调用次数", f"{total_calls:,}")
k3.metric("Tokens", f"{total_tokens:,}")
k4.metric("日均花费", f"¥{total/max(period_days,1):,.2f}")

st.divider()

# --------------------------------------------------------------------------- #
# 趋势：按日花费
# --------------------------------------------------------------------------- #
st.subheader("📈 每日花费趋势")
daily = df.groupby(df["Date"].dt.date)["Amount"].sum().reset_index()
daily.columns = ["日期", "花费"]
st.line_chart(daily.set_index("日期"), height=300)

# --------------------------------------------------------------------------- #
# 两列：成员排名 + 渠道排名
# --------------------------------------------------------------------------- #
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("👤 按成员花费")
    if "Member" in df.columns:
        by_member = df.groupby("Member")["Amount"].sum().sort_values(ascending=False).reset_index()
        by_member.columns = ["成员", "花费"]
        st.dataframe(by_member, use_container_width=True, hide_index=True)
        st.bar_chart(by_member.set_index("成员"), height=250)
    else:
        st.caption("无 Member 字段")

with col_b:
    st.subheader("🔀 按渠道花费")
    if "Channel" in df.columns:
        by_ch = df.groupby("Channel")["Amount"].sum().sort_values(ascending=False).reset_index()
        by_ch.columns = ["渠道", "花费"]
        st.dataframe(by_ch, use_container_width=True, hide_index=True)
        st.bar_chart(by_ch.set_index("渠道"), height=250)
    else:
        st.caption("无 Channel 字段")

# --------------------------------------------------------------------------- #
# 三档分组占比 + 模型排名
# --------------------------------------------------------------------------- #
col_c, col_d = st.columns(2)
with col_c:
    st.subheader("🎯 三档分组占比")
    if "Group" in df.columns and df["Group"].notna().any():
        by_grp = df.groupby("Group")["Amount"].sum()
        # 确保三档都显示，同时保留其它自定义分组
        for g in ("draft", "standard", "final"):
            if g not in by_grp.index:
                by_grp[g] = 0
        # 三档优先排前面，其余跟后
        ordered = [g for g in ("draft", "standard", "final") if g in by_grp.index]
        ordered += [g for g in by_grp.index if g not in ordered]
        by_grp = by_grp[ordered]
        st.bar_chart(by_grp)
        st.caption("draft=草稿(便宜) / standard=日常 / final=成片(贵)。"
                   "final 占比高说明可能存在滥用高质档试错。")
    else:
        st.caption("无 Group 字段")

with col_d:
    st.subheader("🤖 按模型花费")
    if "Model" in df.columns:
        by_model = df.groupby("Model")["Amount"].sum().sort_values(ascending=False).head(10).reset_index()
        by_model.columns = ["模型", "花费"]
        st.dataframe(by_model, use_container_width=True, hide_index=True)
    else:
        st.caption("无 Model 字段")

st.divider()

# --------------------------------------------------------------------------- #
# 明细表
# --------------------------------------------------------------------------- #
with st.expander("📋 查看明细数据", expanded=False):
    show_cols = [c for c in ("Date", "Member", "Channel", "Model", "Group",
                             "Calls", "Tokens", "Amount") if c in df.columns]
    st.dataframe(df[show_cols].sort_values("Date", ascending=False),
                 use_container_width=True, hide_index=True)

st.caption("数据由 cost-sync 自动从 New-API 同步而来。"
           "如需调整，改 cost-sync 的 cron 或运行 `python sync.py --days 7`。")
