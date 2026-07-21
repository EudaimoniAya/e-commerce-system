#!/usr/bin/env bash
# Task 5.1：买家订单 API curl 烟雾测试
# 闭环：下单 → pay → shipments → confirm-receipt；短 TTL 懒释放
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

bash scripts/devbox_mysql_up.sh >/dev/null 2>&1
uv run alembic upgrade head >/dev/null

# 默认 TTL 跑主流程；Part 2 单独起短 TTL 进程
export ORDER_RESERVATION_TTL_SECONDS="${ORDER_RESERVATION_TTL_SECONDS:-86400}"

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
trap 'kill "${SERVER_PID}" 2>/dev/null || true' EXIT

wait_ready() {
  for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
      return 0
    fi
    if [ "${i}" -eq 30 ]; then
      echo "server not ready" >&2
      exit 1
    fi
    sleep 1
  done
}

wait_ready

TS="$(date +%s)"
ADMIN_EMAIL="114514yyut@qq.com"
ADMIN_PASSWORD="1919810810"
SELLER_EMAIL="order-seller-${TS}@example.com"
BUYER_EMAIL="order-buyer-${TS}@example.com"
PASSWORD="password123"
SHOP_NAME="order-shop-${TS}"
PRODUCT_NAME="order-product-${TS}"
CATEGORY_NAME="order-cat-${TS}"

json_field() {
  local body="$1"
  local field="$2"
  printf '%s' "${body}" | python3 -c "import json,sys; print(json.load(sys.stdin)['${field}'])"
}

echo "=== admin login ==="
ADMIN=$(curl -sS -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}")
ADMIN_TOKEN=$(json_field "${ADMIN}" "access_token")

echo "=== create category ==="
CAT=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/categories \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d "{\"name\":\"${CATEGORY_NAME}\",\"description\":\"curl smoke\"}")
echo "${CAT}"
CAT_BODY="${CAT%HTTP:*}"
CATEGORY_ID=$(json_field "${CAT_BODY}" "id")

echo "=== seller register ==="
SELLER=$(curl -sS -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${SELLER_EMAIL}\",\"password\":\"${PASSWORD}\"}")
SELLER_TOKEN=$(json_field "${SELLER}" "access_token")

echo "=== create shop ==="
SHOP=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/shops \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SELLER_TOKEN}" \
  -d "{\"name\":\"${SHOP_NAME}\",\"description\":\"curl smoke shop\"}")
echo "${SHOP}"

echo "=== create published product ==="
PRODUCT=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SELLER_TOKEN}" \
  -d "{\"name\":\"${PRODUCT_NAME}\",\"price\":\"88.00\",\"stock\":20,\"description\":\"curl\",\"is_published\":true,\"category_ids\":[\"${CATEGORY_ID}\"],\"primary_category_id\":\"${CATEGORY_ID}\"}")
echo "${PRODUCT}"
PRODUCT_BODY="${PRODUCT%HTTP:*}"
PRODUCT_ID=$(json_field "${PRODUCT_BODY}" "id")

echo "=== buyer register ==="
BUYER=$(curl -sS -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${BUYER_EMAIL}\",\"password\":\"${PASSWORD}\"}")
BUYER_TOKEN=$(json_field "${BUYER}" "access_token")

echo "=== create order ==="
ORDER=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BUYER_TOKEN}" \
  -d "{\"items\":[{\"product_id\":\"${PRODUCT_ID}\",\"qty\":2}]}")
echo "${ORDER}"
ORDER_BODY="${ORDER%HTTP:*}"
ORDER_ID=$(json_field "${ORDER_BODY}" "id")
ORDER_STATUS=$(json_field "${ORDER_BODY}" "status")
if [ "${ORDER_STATUS}" != "awaiting_payment" ]; then
  echo "expected awaiting_payment, got ${ORDER_STATUS}" >&2
  exit 1
fi

echo "=== pay order ==="
PAID=$(curl -sS -w "\nHTTP:%{http_code}" -X POST "http://127.0.0.1:8000/orders/${ORDER_ID}/pay" \
  -H "Authorization: Bearer ${BUYER_TOKEN}")
echo "${PAID}"
PAID_BODY="${PAID%HTTP:*}"
if [ "$(json_field "${PAID_BODY}" "status")" != "confirmed" ]; then
  echo "pay failed" >&2
  exit 1
fi

echo "=== create shipment ==="
SHIP=$(curl -sS -w "\nHTTP:%{http_code}" -X POST "http://127.0.0.1:8000/orders/${ORDER_ID}/shipments" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SELLER_TOKEN}" \
  -d '{"note":"curl smoke shipment"}')
echo "${SHIP}"
SHIP_BODY="${SHIP%HTTP:*}"
if [ "$(json_field "${SHIP_BODY}" "status")" != "shipped" ]; then
  echo "shipment failed" >&2
  exit 1
fi

echo "=== confirm receipt ==="
DONE=$(curl -sS -w "\nHTTP:%{http_code}" -X POST "http://127.0.0.1:8000/orders/${ORDER_ID}/confirm-receipt" \
  -H "Authorization: Bearer ${BUYER_TOKEN}")
echo "${DONE}"
DONE_BODY="${DONE%HTTP:*}"
if [ "$(json_field "${DONE_BODY}" "status")" != "completed" ]; then
  echo "confirm-receipt failed" >&2
  exit 1
fi

echo "=== main flow OK: awaiting_payment → confirmed → shipped → completed ==="

# ── Part 2：短 TTL 懒释放（需重启服务以加载新 TTL）──
kill "${SERVER_PID}" 2>/dev/null || true
export ORDER_RESERVATION_TTL_SECONDS=2
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
wait_ready

echo "=== short TTL: create order ==="
EXPIRE_ORDER=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BUYER_TOKEN}" \
  -d "{\"items\":[{\"product_id\":\"${PRODUCT_ID}\",\"qty\":1}]}")
echo "${EXPIRE_ORDER}"
EXPIRE_ORDER_BODY="${EXPIRE_ORDER%HTTP:*}"
EXPIRE_ORDER_ID=$(json_field "${EXPIRE_ORDER_BODY}" "id")

echo "=== wait for TTL (3s) ==="
sleep 3

echo "=== GET order triggers lazy expire ==="
EXPIRED=$(curl -sS -w "\nHTTP:%{http_code}" "http://127.0.0.1:8000/orders/${EXPIRE_ORDER_ID}" \
  -H "Authorization: Bearer ${BUYER_TOKEN}")
echo "${EXPIRED}"
EXPIRED_BODY="${EXPIRED%HTTP:*}"
EXPIRED_STATUS=$(json_field "${EXPIRED_BODY}" "status")
EXPIRED_REASON=$(printf '%s' "${EXPIRED_BODY}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cancel_reason'))")
if [ "${EXPIRED_STATUS}" != "cancelled" ] || [ "${EXPIRED_REASON}" != "expired" ]; then
  echo "lazy expire failed: status=${EXPIRED_STATUS} cancel_reason=${EXPIRED_REASON}" >&2
  exit 1
fi

echo "=== lazy expire OK: cancelled / expired ==="
echo "=== ordering curl smoke passed ==="
