#!/usr/bin/env bash
# 备份 MangaRouter data 目录（MySQL 卷 + MinIO）
# 用法：sudo bash deploy/backup.sh
# 可选环境变量：BACKUP_DIR=/var/backups/mangarouter  KEEP_DAYS=7
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/mangarouter}"
KEEP_DAYS="${KEEP_DAYS:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[*] 备份 $ROOT/data → $BACKUP_DIR/manga-$STAMP.tar.gz"
tar -C "$ROOT" -czf "$BACKUP_DIR/manga-$STAMP.tar.gz" data .env 2>/dev/null || \
  tar -C "$ROOT" -czf "$BACKUP_DIR/manga-$STAMP.tar.gz" data

echo "[*] 清理 ${KEEP_DAYS} 天前备份"
find "$BACKUP_DIR" -name 'manga-*.tar.gz' -mtime +"$KEEP_DAYS" -delete || true

# 若已安装腾讯云 coscli 且配置了 COS_BUCKET，则上传
if command -v coscli >/dev/null 2>&1 && [[ -n "${COS_BUCKET:-}" ]]; then
  echo "[*] 上传到 COS $COS_BUCKET"
  coscli cp "$BACKUP_DIR/manga-$STAMP.tar.gz" "cos://$COS_BUCKET/mangarouter/"
fi

echo "[*] 完成：$BACKUP_DIR/manga-$STAMP.tar.gz"
echo "    恢复：停 compose → 解压 data → docker compose up -d（建议先演练一次，记录 RTO）"
