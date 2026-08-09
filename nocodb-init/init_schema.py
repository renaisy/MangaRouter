#!/usr/bin/env python3
"""NocoDB 协作平台表结构一键初始化。

在指定的 NocoDB Base（工作区）里创建三张表：
  1. Projects   项目表
  2. Storyboards 分镜表（提交工具读取/回填的就是这张）
  3. Costs      成本表（用于人工记录或后续从 New-API 同步）

使用方法：
  1. 先在 NocoDB 网页里创建一个空的 Base，记下它的 baseId（URL 里形如 p_xxxxx）
  2. 在 NocoDB「项目设置 → API」里生成一个 API Token
  3. 运行：
       pip install httpx
       python init_schema.py
     按提示输入地址、token、baseId
"""
from __future__ import annotations

import os
import sys
import httpx

# --------------------------------------------------------------------------- #
# 表结构定义（NocoDB v2 API 字段格式）
# --------------------------------------------------------------------------- #
PROJECTS_COLUMNS = [
    {"title": "剧名", "column_name": "Title", "uidt": "SingleLineText", "rqd": True, "pk": False},
    {"title": "集数", "column_name": "Episodes", "uidt": "Number"},
    {"title": "负责人", "column_name": "Owner", "uidt": "SingleLineText"},
    {"title": "截止日期", "column_name": "Deadline", "uidt": "Date"},
    {"title": "状态", "column_name": "Status", "uidt": "SingleSelect",
     "dtxp": "策划中,制作中,审核中,已完成,搁置"},
    {"title": "总预算(元)", "column_name": "Budget", "uidt": "Number", "dt": "decimal"},
    {"title": "备注", "column_name": "Remark", "uidt": "LongText"},
]

STORYBOARDS_COLUMNS = [
    {"title": "项目", "column_name": "Project", "uidt": "SingleLineText"},
    {"title": "集", "column_name": "Episode", "uidt": "SingleLineText"},
    {"title": "镜头号", "column_name": "ShotNo", "uidt": "SingleLineText"},
    {"title": "提示词", "column_name": "Prompt", "uidt": "LongText", "rqd": True},
    {"title": "参考图URL", "column_name": "ImageUrl", "uidt": "URL"},
    {"title": "重要级", "column_name": "Priority", "uidt": "SingleSelect",
     "dtxp": "草稿,日常,成片", "dtxs": "日常"},
    {"title": "指定模型", "column_name": "Model", "uidt": "SingleLineText"},
    {"title": "状态", "column_name": "Status", "uidt": "SingleSelect",
     "dtxp": "pending,running,succeeded,failed", "dtxs": "pending"},
    {"title": "成片链接", "column_name": "VideoUrl", "uidt": "URL"},
    {"title": "MinIO路径", "column_name": "MinioPath", "uidt": "SingleLineText"},
    {"title": "提交时间", "column_name": "SubmittedAt", "uidt": "DateTime"},
    {"title": "耗时(秒)", "column_name": "DurationSec", "uidt": "Number"},
    {"title": "花费(元)", "column_name": "Cost", "uidt": "Number", "dt": "decimal"},
    {"title": "审核意见", "column_name": "Review", "uidt": "LongText"},
    {"title": "审核状态", "column_name": "ReviewStatus", "uidt": "SingleSelect",
     "dtxp": "待审核,通过,打回"},
    {"title": "备注", "column_name": "Remark", "uidt": "LongText"},
]

COSTS_COLUMNS = [
    {"title": "日期", "column_name": "Date", "uidt": "Date", "rqd": True},
    {"title": "项目", "column_name": "Project", "uidt": "SingleLineText"},
    {"title": "人员", "column_name": "Member", "uidt": "SingleLineText"},
    {"title": "渠道", "column_name": "Channel", "uidt": "SingleLineText"},
    {"title": "模型", "column_name": "Model", "uidt": "SingleLineText"},
    {"title": "分组", "column_name": "Group", "uidt": "SingleLineText"},
    {"title": "调用次数", "column_name": "Calls", "uidt": "Number"},
    {"title": "Tokens", "column_name": "Tokens", "uidt": "Number"},
    {"title": "花费(元)", "column_name": "Amount", "uidt": "Number", "dt": "decimal"},
    {"title": "备注", "column_name": "Remark", "uidt": "LongText"},
]

# 提示词模板库：沉淀成功提示词供全员复用，降低调用次数（省钱）
# 与 docs/提示词工程最佳实践.md 配合使用
PROMPT_TEMPLATES_COLUMNS = [
    {"title": "场景类型", "column_name": "SceneType", "uidt": "SingleSelect",
     "dtxp": "角色登场,情绪特写,动作戏,环境空镜,角色一致性,转场,其它",
     "dtxs": "角色登场"},
    {"title": "模板名", "column_name": "Name", "uidt": "SingleLineText", "rqd": True},
    {"title": "提示词", "column_name": "Prompt", "uidt": "LongText", "rqd": True},
    {"title": "输入模式", "column_name": "InputMode", "uidt": "SingleSelect",
     "dtxp": "文生视频,首帧,首尾帧,多参考图", "dtxs": "文生视频"},
    {"title": "所用模型", "column_name": "Model", "uidt": "SingleLineText"},
    {"title": "推荐重要级", "column_name": "Priority", "uidt": "SingleSelect",
     "dtxp": "草稿,日常,成片"},
    {"title": "Seed", "column_name": "Seed", "uidt": "Number"},
    {"title": "效果评分", "column_name": "Rating", "uidt": "Number"},
    {"title": "缩略图URL", "column_name": "ThumbnailUrl", "uidt": "URL"},
    {"title": "来源项目", "column_name": "Project", "uidt": "SingleLineText"},
    {"title": "贡献人", "column_name": "Contributor", "uidt": "SingleLineText"},
    {"title": "标签", "column_name": "Tags", "uidt": "SingleLineText"},
    {"title": "使用次数", "column_name": "UseCount", "uidt": "Number"},
    {"title": "备注", "column_name": "Remark", "uidt": "LongText"},
]


# NocoDB uidt → MySQL 底层类型(dt) 映射
# 不再全部用 character varying（否则数值/日期排序聚合退化为字符串比较）
# 字段定义里可显式给 "dt" 覆盖本表（金额字段用 decimal）
UIDT_TO_DT = {
    "Number": "int",
    "Date": "date",
    "DateTime": "timestamp",
    "SingleLineText": "varchar",
    "LongText": "text",
    "SingleSelect": "varchar",
    "MultiSelect": "varchar",
    "URL": "varchar",
}


def resolve_dt(col: dict) -> str:
    """解析单列的底层类型：字段显式 dt 优先，否则按 uidt 映射，兜底 varchar。"""
    return col.get("dt") or UIDT_TO_DT.get(col.get("uidt", ""), "varchar")


def build_columns_payload(columns: list[dict]) -> list[dict]:
    """把列定义转成 NocoDB 建表 API 接受的格式。抽出来便于单测。"""
    result = []
    for c in columns:
        item = {
            "column_name": c["column_name"],
            "uidt": c["uidt"],
            "dt": resolve_dt(c),
            "title": c.get("title", c["column_name"]),
        }
        if c.get("rqd"):
            item["rqd"] = True
        if c.get("pk"):
            item["pk"] = True
        if c.get("dtxp"):
            item["dtxp"] = c["dtxp"]
        if c.get("dtxs"):
            item["dtxs"] = c["dtxs"]
        result.append(item)
    return result


def create_table(base_url: str, token: str, base_id: str, table_title: str,
                 columns: list[dict]) -> str:
    """在指定 Base 里创建一张表，返回 tableId。

    v0.3.2 改进：
      - dt 按 uidt 映射（不再全部 character varying）
      - 返回值校验：拿不到 tableId 抛异常而非返回空串
    """
    url = f"{base_url}/api/v2/meta/bases/{base_id}/tables"
    headers = {"xc-token": token}
    payload = {
        "table_name": table_title,
        "title": table_title,
        "columns": build_columns_payload(columns),
    }
    r = httpx.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    tid = data.get("id") or data.get("tbl_id")
    if not tid:
        raise RuntimeError(f"建表 {table_title} 未返回 tableId：{data}")
    return str(tid)


def list_existing_tables(base_url: str, token: str, base_id: str) -> set[str]:
    """列出 Base 里已存在的表名集合，用于建表幂等。"""
    url = f"{base_url}/api/v2/meta/bases/{base_id}/tables"
    headers = {"xc-token": token}
    r = httpx.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    # 响应可能是 {list: [...]} 或直接是 [...]
    items = data.get("list") if isinstance(data, dict) else data
    return {str(t.get("title") or t.get("table_name")) for t in (items or [])}


# 四张表清单（抽到模块级，便于单测与 main 复用）
ALL_TABLES = [
    ("Projects", PROJECTS_COLUMNS),
    ("Storyboards", STORYBOARDS_COLUMNS),
    ("Costs", COSTS_COLUMNS),
    ("PromptTemplates", PROMPT_TEMPLATES_COLUMNS),
]

_HINT_FOR_TABLE = {
    "Storyboards": "→ 把这个 tableId 填到「分镜提交工具」",
    "Costs": "→ 把这个 tableId 填到 .env 的 COST_NOCODB_TABLE_ID（计费同步用）",
    "PromptTemplates": "→ 提示词模板库，沉淀成功提示词供全员复用",
}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="NocoDB 协作平台表结构初始化")
    parser.add_argument("--base-url", default=os.environ.get("NOCODB_BASE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("NOCODB_TOKEN", ""))
    parser.add_argument("--base-id", default=os.environ.get("NOCODB_BASE_ID", ""))
    parser.add_argument("--interactive", action="store_true",
                        help="交互式输入（环境变量/参数都缺时用 input 兜底）")
    args = parser.parse_args()

    print("=" * 60)
    print("  NocoDB 协作平台表结构初始化")
    print("=" * 60)

    # 环境变量/命令行参数优先；--interactive 时才用 input 兜底
    base_url = args.base_url
    token = args.token
    base_id = args.base_id
    if args.interactive:
        base_url = base_url or input("NocoDB 地址 (默认 http://localhost:18080): ").strip() or "http://localhost:18080"
        token = token or input("NocoDB API Token: ").strip()
        base_id = base_id or input("Base ID (URL 里 p_xxx): ").strip()

    if not (token and base_id):
        print("✗ 必须提供 API Token 和 Base ID")
        print("  用法：python init_schema.py --token <t> --base-id <p_xxx>")
        print("  或设环境变量 NOCODB_TOKEN / NOCODB_BASE_ID")
        print("  或加 --interactive 交互式输入")
        return 1
    if not base_url:
        base_url = "http://localhost:18080"

    # 幂等：先查已存在的表，已存在则跳过
    try:
        existing = list_existing_tables(base_url, token, base_id)
    except Exception as e:
        print(f"⚠️ 无法查询已有表（{e}），将直接尝试建表（已存在会失败）")
        existing = set()

    todo = [(t, c) for t, c in ALL_TABLES if t not in existing]
    skipped = [t for t, _ in ALL_TABLES if t in existing]
    for t in skipped:
        print(f"  ⏭️  {t:<18} 已存在，跳过")

    if not todo:
        print("\n所有表均已存在，无需创建。")
        return 0

    print(f"\n将创建 {len(todo)} 张表…\n")
    failed = 0
    for title, cols in todo:
        try:
            tid = create_table(base_url, token, base_id, title, cols)
            print(f"  ✅ {title:<18} 创建成功  tableId = {tid}")
            hint = _HINT_FOR_TABLE.get(title)
            if hint:
                print(f"      {hint}")
        except httpx.HTTPStatusError as e:
            failed += 1
            print(f"  ❌ {title} 创建失败：HTTP {e.response.status_code} {e.response.text[:200]}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {title} 创建失败：{e}")
    print("\n完成。接下来可以在 NocoDB 网页里给字段加上中文显示名、调整视图。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
