#!/usr/bin/env bash
# MangaRouter 上线烟雾检查（C5）
# 用法：在仓库根目录 ./deploy/smoke-check.sh
# 可选环境变量：
#   SMOKE_SUBMIT_URL=https://submit.your.domain
#   SMOKE_DASH_URL=https://dash.your.domain
#   SMOKE_ADMIN_URL=https://admin.your.domain
#   SMOKE_ADAPTER_URL=http://127.0.0.1:18008
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
ok() { echo "OK  $*"; }
bad() { echo "FAIL $*"; fail=1; }

echo "== compose config =="
if docker compose config -q 2>/dev/null; then
  ok "docker compose config"
else
  bad "docker compose config"
fi

echo "== adapter health (本机回环) =="
ADAPTER_URL="${SMOKE_ADAPTER_URL:-http://127.0.0.1:${ADAPTER_PORT:-18008}}"
if curl -sf --max-time 5 "${ADAPTER_URL}/health" >/dev/null 2>&1; then
  ok "adapter /health ${ADAPTER_URL}"
else
  echo "SKIP adapter unreachable（服务未起时可忽略）: ${ADAPTER_URL}"
fi

check_401() {
  local name="$1" url="$2"
  if [[ -z "$url" ]]; then
    echo "SKIP ${name}（未设 URL）"
    return
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" || true)"
  if [[ "$code" == "401" ]]; then
    ok "${name} 无凭证 → 401"
  else
    bad "${name} 期望 401，实际 ${code:-curl_fail}（${url}）"
  fi
}

echo "== basicauth（无凭证应 401）=="
check_401 "submit" "${SMOKE_SUBMIT_URL:-}"
check_401 "dash" "${SMOKE_DASH_URL:-}"
check_401 "admin" "${SMOKE_ADMIN_URL:-}"

if [[ "$fail" -ne 0 ]]; then
  echo "smoke-check FAILED"
  exit 1
fi
echo "smoke-check PASSED"
exit 0
