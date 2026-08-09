#!/usr/bin/env python3
"""扫 NocoDB Status=running 的任务，轮询 New-API/适配器，归档并回填。"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from minio_store import archive_video_from_url, project_object_prefix
from newapi_submit import get_task, group_for_priority, token_for_group
from nocodb_client import NocoDBStoryboards
from webhook_notify import notify_review

TZ = ZoneInfo(os.environ.get("TZ", "Asia/Shanghai") or "Asia/Shanghai")
_fail_count = 0


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def log_event(level: str, **fields: object) -> None:
    payload = {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "level": level, **fields}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def within_active_hours(now: datetime | None = None) -> bool:
    """WORKER_ACTIVE_HOURS=0-6 → 仅该小时闭开区间；空=全天。"""
    raw = _env("WORKER_ACTIVE_HOURS")
    if not raw:
        return True
    try:
        start_s, end_s = raw.split("-", 1)
        start, end = int(start_s), int(end_s)
    except Exception:
        log_event("error", msg="invalid WORKER_ACTIVE_HOURS", value=raw)
        return True
    hour = (now or datetime.now(TZ)).hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    # 跨午夜：22-6
    return hour >= start or hour < end


def process_row(nc: NocoDBStoryboards, row: dict) -> None:
    global _fail_count
    rid = nc.record_id(row)
    if not rid:
        return
    task_id = str(row.get("TaskId") or "").strip()
    if not task_id:
        nc.patch_record(rid, {"Status": "failed", "ErrorMsg": "缺少 TaskId"})
        _fail_count += 1
        log_event("error", event="missing_task_id", record_id=rid, fail_count=_fail_count)
        return

    priority = str(row.get("Priority") or "日常")
    group = group_for_priority(priority)
    base = _env("SUBMIT_NEWAPI_BASE_URL", "http://localhost:13000")
    token = token_for_group(group)
    if not token:
        log_event("warn", event="skip_no_token", record_id=rid, group=group)
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
        _fail_count += 1
        log_event("error", event="task_failed", record_id=rid, error=result.get("error"),
                  fail_count=_fail_count)
        return
    if status != "succeeded" or not result.get("video_url"):
        return

    video_url = result["video_url"]
    project_key = str(row.get("ProjectKey") or row.get("Project") or "default")
    episode = str(row.get("Episode") or "ep")
    shot = str(row.get("ShotNo") or rid)
    prefix = project_object_prefix(project_key, episode, str(shot))
    try:
        minio_path, share = archive_video_from_url(video_url, prefix)
    except Exception as e:
        nc.patch_record(rid, {
            "Status": "succeeded",
            "VideoUrl": video_url,
            "ErrorMsg": f"归档失败仍保留方舟链: {e}"[:500],
        })
        _fail_count += 1
        log_event("error", event="archive_fail", record_id=rid, error=str(e), fail_count=_fail_count)
        return

    fields = {
        "Status": "succeeded",
        "VideoUrl": video_url,
        "MinioPath": minio_path,
        "ShareUrl": share,
        "ErrorMsg": "",
        "ProjectKey": project_key,
        "SubmittedAt": datetime.now(TZ).isoformat(timespec="seconds"),
    }
    nc.patch_record(rid, fields)
    notify_review(
        f"[MangaRouter] 成片就绪\n"
        f"ProjectKey={project_key} 集={episode} 镜头={shot}\n"
        f"分享链: {share}"
    )
    log_event("info", event="succeeded", record_id=rid, minio_path=minio_path)


def main() -> int:
    poll = int(_env("WORKER_POLL_SECONDS", "15") or "15")
    log_event("info", event="worker_start", poll_seconds=poll,
              active_hours=_env("WORKER_ACTIVE_HOURS") or "all")
    while True:
        if not within_active_hours():
            log_event("info", event="outside_window", skip=True)
            time.sleep(poll)
            continue
        nc = NocoDBStoryboards()
        try:
            if not nc.is_configured():
                log_event("warn", event="nocodb_unconfigured")
            else:
                rows = nc.list_by_status("running")
                for row in rows:
                    try:
                        process_row(nc, row)
                    except Exception as e:
                        global _fail_count
                        _fail_count += 1
                        log_event("error", event="process_exception", error=str(e),
                                  fail_count=_fail_count)
        finally:
            nc.close()
        time.sleep(poll)


if __name__ == "__main__":
    sys.exit(main())
