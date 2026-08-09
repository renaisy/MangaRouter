#!/usr/bin/env bash
# 腾讯云 VPS 初始化脚本（Ubuntu 22.04 / 24.04）
# 用法：sudo bash deploy/vps-setup.sh
set -euo pipefail

echo "=== MangaRouter VPS 初始化 ==="

if [[ "${EUID}" -ne 0 ]]; then
  echo "请用 root 运行：sudo bash deploy/vps-setup.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg ufw git

# Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "[*] 安装 Docker…"
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

# Caddy（HTTPS 反代）
if ! command -v caddy >/dev/null 2>&1; then
  echo "[*] 安装 Caddy…"
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

# 防火墙：仅 SSH + HTTP/HTTPS
echo "[*] 配置 ufw…"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable || true

echo
echo "=== 下一步 ==="
echo "1. 把本仓库放到 /opt/MangaRouter（或任意目录）"
echo "2. cp .env.example .env && nano .env   # 填密码、域名、VOLC_API_KEY"
echo "3. 编辑 deploy/Caddyfile，把 your.domain 换成真实域名"
echo "4. docker compose up -d"
echo "5. sudo cp deploy/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy"
echo "6. 腾讯云安全组放行 22/80/443（不要放行 13000 等业务端口）"
echo
echo "完成。详见 docs/部署指南.md"
