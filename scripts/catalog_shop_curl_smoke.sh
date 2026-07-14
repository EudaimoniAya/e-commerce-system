#!/usr/bin/env bash
# Task 5.1：店铺 API curl 烟雾测试（注册 → 开店 → me → patch closed → 公开 GET）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

bash scripts/devbox_mysql_up.sh >/dev/null 2>&1
uv run alembic upgrade head >/dev/null

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
trap 'kill "${SERVER_PID}" 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
    break
  fi
  if [ "${i}" -eq 30 ]; then
    echo "server not ready" >&2
    exit 1
  fi
  sleep 1
done

EMAIL="curl-smoke-$(date +%s)@example.com"
PASSWORD="password123"
SHOP_NAME="curl-shop-$(date +%s)"

echo "=== register ==="
REG=$(curl -sS -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")
echo "${REG}"
TOKEN=$(printf '%s' "${REG}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

echo "=== create shop ==="
CREATE=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/shops \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "{\"name\":\"${SHOP_NAME}\",\"description\":\"curl smoke\"}")
echo "${CREATE}"
SHOP_ID=$(printf '%s' "${CREATE}" | python3 -c 'import json,sys; body=sys.stdin.read().rsplit("HTTP:",1)[0]; print(json.loads(body)["id"])')

echo "=== get my shop ==="
curl -sS -w "\nHTTP:%{http_code}\n" http://127.0.0.1:8000/shops/me \
  -H "Authorization: Bearer ${TOKEN}"

echo "=== patch closed ==="
curl -sS -w "\nHTTP:%{http_code}\n" -X PATCH http://127.0.0.1:8000/shops/me \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"status":"closed"}'

echo "=== public get ==="
curl -sS -w "\nHTTP:%{http_code}\n" "http://127.0.0.1:8000/shops/${SHOP_ID}"
