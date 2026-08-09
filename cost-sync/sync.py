#!/usr/bin/env python3
"""计费同步主入口：把 New-API 的消费日志汇总后写入 NocoDB Costs 表。

用法：
  # 同步昨天
  python sync.py

  # 同步最近 7 天
  python sync.py --days 7

  # 同步指定日期
  python sync.py --date 2026-08-08

  # 试运行（只统计不写入）
  python sync.py --dry-run

环境变量见 config.py。建议配成定时任务（cron / Windows 任务计划）每天凌晨跑一次。

定时任务示例（Linux cron，每天 1:00 同步昨天）：
  0 1 * * * cd /path/seedance-hub/cost-sync && python sync.py >> /var/log/cost-sync.log 2>&1
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from aggregator import CN_TZ, aggregate
from config import get_config
from newapi_client import NewAPIClient
from nocodb_writer import NocoDBWriter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="New-API 消费日志 → NocoDB Costs 表同步")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=1,
                   help="同步最近 N 天（默认 1，即昨天）")
    g.add_argument("--date", type=str,
                   help="同步指定日期 YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", help="只统计不写入")
    p.add_argument("--project", type=str, default="", help="标注到 Project 字段")
    return p.parse_args()


def day_range(date_str: str | None, days: int) -> tuple[int, int, str]:
    """计算要同步的时间范围（按北京时间），返回 (start_ts, end_ts, 描述)。"""
    now = datetime.now(tz=CN_TZ)
    if date_str:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)
    else:
        # 默认同步「昨天」：days=1 表示昨天一天
        target = now - timedelta(days=days)
        target = target.replace(hour=0, minute=0, second=0, microsecond=0)
    start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_str:
        end = start + timedelta(days=1)
        desc = start.strftime("%Y-%m-%d")
    else:
        # --days N：从 N 天前 0 点 到 现在
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        desc = f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d %H:%M')}"
    return int(start.timestamp()), int(end.timestamp()), desc


def main() -> int:
    args = parse_args()
    cfg = get_config()
    if not cfg.is_complete():
        print("✗ 配置不完整，请设置环境变量（见 config.py）：")
        print("  COST_NEWAPI_TOKEN / COST_NOCODB_TOKEN / COST_NOCODB_TABLE_ID")
        return 1

    start_ts, end_ts, desc = day_range(args.date, args.days)
    print(f"=== 计费同步 {desc} ===")

    # 1. 拉日志
    print(f"[1/3] 拉取 New-API 消费日志 ({cfg.newapi_base_url}) …")
    nc = NewAPIClient(cfg.newapi_base_url, cfg.newapi_token)
    try:
        entries = list(nc.fetch_logs(start_ts, end_ts, log_type=2))
    finally:
        nc.close()
    total_yuan = round(sum(e.amount_yuan for e in entries), 2)
    print(f"      共 {len(entries)} 条消费记录，合计 ¥{total_yuan}")
    if not entries:
        print("      无消费记录，结束。")
        return 0

    # 2. 聚合
    print("[2/3] 按日×成员×模型×渠道×分组聚合 …")
    agg = aggregate(entries)
    print(f"      聚合为 {len(agg)} 个汇总行")

    if args.dry_run:
        print("[dry-run] 不写入，预览前 20 行：")
        for i, (k, v) in enumerate(sorted(agg.items())):
            if i >= 20:
                print(f"      … 还有 {len(agg) - 20} 行")
                break
            print(f"      {k.date} | {k.member:<12} | {k.model:<28} | "
                  f"{k.channel:<10} | {v.calls}次 ¥{v.amount_yuan}")
        return 0

    # 3. 写入
    print(f"[3/3] 写入 NocoDB Costs 表 ({cfg.nocodb_table_id}) …")
    nw = NocoDBWriter(cfg.nocodb_base_url, cfg.nocodb_token, cfg.nocodb_table_id)
    try:
        stats = nw.upsert_many(agg.items(), project=args.project)
    finally:
        nw.close()
    print(f"      ✅ 完成：新增 {stats['inserted']} 行，更新 {stats['updated']} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
