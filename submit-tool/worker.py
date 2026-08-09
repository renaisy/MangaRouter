#!/usr/bin/env python3
"""扫 NocoDB Status=running 的任务，轮询 New-API/适配器，归档并回填。"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

from minio_store import archive_video_from_url
from newapi_submit import get_task, group_for_priority, token_for_group
from nocodb_client import NocoDBStoryboards
from webhook_notify import notify_review


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def process_row(nc: NocoDBStoryboards, row: dict) -> None:
    rid = nc.record_id(row)
    if not rid:
        return
    task_id = str(row.get("TaskId") or "").strip()
    if not task_id:
        nc.patch_record(rid, {"Status": "failed", "ErrorMsg": "缺少 TaskId"})
        return

    priority = str(row.get("Priority") or "日常")
    group = group_for_priority(priority)
    base = _env("SUBMIT_NEWAPI_BASE_URL", "http://localhost:13000")
    token = token_for_group(group)
    if not token:
        print(f"[worker] 无 token，跳过 Id={rid}")
        return

    result = get_task(base, token, task_id, group=group)
    status = str(result.get("status") or "").lower()
    if status in ("queued", "running", "pending", "processing"):
        return
    if status == "failed" or result.get("error"):
        nc.patch_record(rid, {
            "Status": "failed",
            "ErrorMsg": str(result.get("error") or "生成失败")[:500],
        })
        print(f"[worker] Id={rid} failed: {result.get('error')}")
        return
    if status != "succeeded" or not result.get("video_url"):
        return

    video_url = result["video_url"]
    project = str(row.get("Project") or "default")
    episode = str(row.get("Episode") or "ep")
    shot = str(row.get("ShotNo") or rid)
    prefix = f"{project}/{episode}/{shot}"
    try:
        minio_path, share = archive_video_from_url(video_url, prefix)
    except Exception as e:
        nc.patch_record(rid, {
            "Status": "succeeded",
            "VideoUrl": video_url,
            "ErrorMsg": f"归档失败仍保留方舟链: {e}"[:500],
        })
        print(f"[worker] Id={rid} archive fail: {e}")
        return

    fields = {
        "Status": "succeeded",
        "VideoUrl": video_url,
        "MinioPath": minio_path,
        "ShareUrl": share,
        "ErrorMsg": "",
        "SubmittedAt": datetime.now().isoformat(timespec="seconds"),
    }
    nc.patch_record(rid, fields)
    notify_review(
        f"[MangaRouter] 成片就绪\n"
        f"项目={project} 集={episode} 镜头={shot}\n"
        f"分享链(7天): {share}"
    )
    print(f"[worker] Id={rid} succeeded → {minio_path}")


def main() -> int:
    poll = int(_env("WORKER_POLL_SECONDS", "15") or "15")
    print(f"[worker] 启动，每 {poll}s 扫描 running 任务")
    while True:
        nc = NocoDBStoryboards()
        try:
            if not nc.is_configured():
                print("[worker] 未配置 NOCODB_TOKEN / STORYBOARDS_TABLE_ID，等待…")
            else:
                rows = nc.list_by_status("running")
                for row in rows:
                    try:
                        process_row(nc, row)
                    except Exception as e:
                        print(f"[worker] 处理失败: {e}")
        finally:
            nc.close()
        time.sleep(poll)


if __name__ == "__main__":
    sys.exit(main())
