#!/usr/bin/env bash
# Task 7.1：手机号认证 API curl 烟雾（send → register → password login → PATCH /users/me）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

bash scripts/devbox_mysql_up.sh >/dev/null 2>&1
bash scripts/devbox_redis_up.sh >/dev/null 2>&1
uv run alembic upgrade head >/dev/null

# 固定 OTP 便于本地烟雾（与 .env.test 中 SMS_OTP_FIXED_CODE 对齐）
export SMS_OTP_FIXED_CODE="${SMS_OTP_FIXED_CODE:-123456}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"

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

PHONE=$(python3 -c "import random; print(f'138{random.randint(0, 99999999):08d}')")
PASSWORD="password123"
OTP="${SMS_OTP_FIXED_CODE}"

echo "=== sms send ==="
curl -sS -w "\nHTTP:%{http_code}\n" -X POST http://127.0.0.1:8000/auth/sms/send \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"${PHONE}\"}"

echo "=== sms register ==="
REG=$(curl -sS -X POST http://127.0.0.1:8000/auth/sms/register \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"${PHONE}\",\"code\":\"${OTP}\",\"password\":\"${PASSWORD}\"}")
echo "${REG}"
TOKEN=$(printf '%s' "${REG}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

echo "=== password login ==="
LOGIN=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"${PHONE}\",\"password\":\"${PASSWORD}\"}")
echo "${LOGIN}"

echo "=== patch profile ==="
curl -sS -w "\nHTTP:%{http_code}\n" -X PATCH http://127.0.0.1:8000/users/me \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"email":"curl-smoke@example.com","nickname":"curl-smoke-user"}'

echo "=== get me ==="
curl -sS -w "\nHTTP:%{http_code}\n" http://127.0.0.1:8000/users/me \
  -H "Authorization: Bearer ${TOKEN}"
