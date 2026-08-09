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
    """计算要同步的时间范围（按北京时间整天对齐），返回 (start_ts, end_ts, 描述)。

    - --date YYYY-MM-DD：同步该日整天 [该日0:00, 次日0:00)
    - --days N：同步过去 N 个完整自然日 [今天0:00 - N天, 今天0:00)
      （默认 days=1 即昨天整天，与 help 描述一致；不含当天未结束的数据，
       避免与覆盖式 upsert 配合时产生"当天数据要等次日才补全"的延迟）
    """
    today_0 = datetime.now(tz=CN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_str:
        start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ)
        end = start + timedelta(days=1)
        desc = start.strftime("%Y-%m-%d")
    else:
        end = today_0
        start = today_0 - timedelta(days=days)
        if days == 1:
            desc = start.strftime("%Y-%m-%d")
        else:
            desc = f"{start.strftime('%Y-%m-%d')} ~ {(end - timedelta(days=1)).strftime('%Y-%m-%d')}"
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
    log_count = 0
    total_yuan = 0.0
    try:
        # 用有状态生成器边拉边聚合，避免大窗口全量入内存
        def _iter_and_count():
            nonlocal log_count, total_yuan
            for e in nc.fetch_logs(start_ts, end_ts, log_type=2):
                log_count += 1
                total_yuan += e.amount_yuan
                yield e

        if args.dry_run:
            # dry-run 需要预览，物化后再统计
            entries = list(_iter_and_count())
            agg = aggregate(entries)
        else:
            # 正式同步：直接把生成器喂给聚合，流式处理
            agg = aggregate(_iter_and_count())
    finally:
        nc.close()
    total_yuan = round(total_yuan, 2)
    print(f"      共 {log_count} 条消费记录，合计 ¥{total_yuan}")
    if log_count == 0:
        print("      无消费记录，结束。")
        return 0

    # 2. 聚合（上面已完成）
    print(f"[2/3] 按日×成员×模型×渠道×分组聚合为 {len(agg)} 个汇总行")

    if args.dry_run:
        print("[dry-run] 不写入，预览前 20 行：")
        for i, (k, v) in enumerate(sorted(agg.items())):
            if i >= 20:
                print(f"      … 还有 {len(agg) - 20} 行")
                break
            print(f"      {k.date} | {k.member:<12} | {k.model:<28} | "
                  f"{k.channel:<10} | {k.group or '-':<8} | {v.calls}次 ¥{v.amount_yuan}")
        return 0

    # 3. 写入
    print(f"[3/3] 写入 NocoDB Costs 表 ({cfg.nocodb_table_id}) …")
    nw = NocoDBWriter(cfg.nocodb_base_url, cfg.nocodb_token, cfg.nocodb_table_id)
    try:
        stats = nw.upsert_many(agg.items(), project=args.project)
    finally:
        nw.close()
    print(f"      完成：新增 {stats['inserted']} 行，更新 {stats['updated']} 行"
          f"，失败 {stats['failed']} 行")
    if stats["failed"] > 0:
        print(f"      ⚠️ 有 {stats['failed']} 行写入失败，请检查上方 [warn] 日志")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
