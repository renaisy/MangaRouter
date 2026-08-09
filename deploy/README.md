# MangaRouter VPS 部署说明（摘要）
#
# 完整步骤见 docs/部署指南.md
#
# 快速路径：
#   sudo bash deploy/vps-setup.sh
#   cp .env.example .env && 编辑
#   编辑 Caddyfile 域名
#   docker compose up -d
#   sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy
