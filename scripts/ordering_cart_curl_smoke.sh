#!/usr/bin/env bash
# Task 6.1：购物车 API curl 烟雾测试
# 闭环：加购 → GET cart → checkout → batch-pay
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

bash scripts/devbox_mysql_up.sh >/dev/null 2>&1
uv run alembic upgrade head >/dev/null

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
SELLER_EMAIL="cart-seller-${TS}@example.com"
BUYER_EMAIL="cart-buyer-${TS}@example.com"
PASSWORD="password123"
SHOP_NAME="cart-shop-${TS}"
PRODUCT_NAME="cart-product-${TS}"
CATEGORY_NAME="cart-cat-${TS}"

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
CAT=$(curl -sS -X POST http://127.0.0.1:8000/categories \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -d "{\"name\":\"${CATEGORY_NAME}\",\"description\":\"cart curl smoke\"}")
CATEGORY_ID=$(json_field "${CAT}" "id")

echo "=== seller register + shop + product ==="
SELLER=$(curl -sS -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${SELLER_EMAIL}\",\"password\":\"${PASSWORD}\"}")
SELLER_TOKEN=$(json_field "${SELLER}" "access_token")

curl -sS -X POST http://127.0.0.1:8000/shops \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SELLER_TOKEN}" \
  -d "{\"name\":\"${SHOP_NAME}\",\"description\":\"cart smoke shop\"}" >/dev/null

PRODUCT=$(curl -sS -X POST http://127.0.0.1:8000/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SELLER_TOKEN}" \
  -d "{\"name\":\"${PRODUCT_NAME}\",\"price\":\"66.00\",\"stock\":20,\"description\":\"curl\",\"is_published\":true,\"category_ids\":[\"${CATEGORY_ID}\"],\"primary_category_id\":\"${CATEGORY_ID}\"}")
PRODUCT_ID=$(json_field "${PRODUCT}" "id")

echo "=== buyer register ==="
BUYER=$(curl -sS -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${BUYER_EMAIL}\",\"password\":\"${PASSWORD}\"}")
BUYER_TOKEN=$(json_field "${BUYER}" "access_token")

echo "=== add to cart ==="
CART_ITEM=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/cart/items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BUYER_TOKEN}" \
  -d "{\"product_id\":\"${PRODUCT_ID}\",\"qty\":2}")
echo "${CART_ITEM}"
CART_ITEM_BODY="${CART_ITEM%HTTP:*}"
CART_ITEM_HTTP="${CART_ITEM##*HTTP:}"
if [ "${CART_ITEM_HTTP}" != "201" ]; then
  echo "add to cart failed HTTP ${CART_ITEM_HTTP}" >&2
  exit 1
fi
CART_ITEM_ID=$(json_field "${CART_ITEM_BODY}" "id")

echo "=== GET cart ==="
CART_LIST=$(curl -sS -w "\nHTTP:%{http_code}" http://127.0.0.1:8000/cart \
  -H "Authorization: Bearer ${BUYER_TOKEN}")
echo "${CART_LIST}"
CART_LIST_HTTP="${CART_LIST##*HTTP:}"
if [ "${CART_LIST_HTTP}" != "200" ]; then
  echo "GET cart failed" >&2
  exit 1
fi

echo "=== checkout ==="
CHECKOUT=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/cart/checkout \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BUYER_TOKEN}" \
  -d "{\"cart_item_ids\":[\"${CART_ITEM_ID}\"]}")
echo "${CHECKOUT}"
CHECKOUT_BODY="${CHECKOUT%HTTP:*}"
CHECKOUT_HTTP="${CHECKOUT##*HTTP:}"
if [ "${CHECKOUT_HTTP}" != "201" ]; then
  echo "checkout failed HTTP ${CHECKOUT_HTTP}" >&2
  exit 1
fi
BATCH_ID=$(json_field "${CHECKOUT_BODY}" "checkout_batch_id")
ORDER_ID=$(printf '%s' "${CHECKOUT_BODY}" | python3 -c "import json,sys; print(json.load(sys.stdin)['orders'][0]['id'])")
ORDER_STATUS=$(printf '%s' "${CHECKOUT_BODY}" | python3 -c "import json,sys; print(json.load(sys.stdin)['orders'][0]['status'])")
if [ "${ORDER_STATUS}" != "awaiting_payment" ]; then
  echo "expected awaiting_payment after checkout, got ${ORDER_STATUS}" >&2
  exit 1
fi

echo "=== GET checkout batch ==="
BATCH=$(curl -sS -w "\nHTTP:%{http_code}" "http://127.0.0.1:8000/orders/checkout-batches/${BATCH_ID}" \
  -H "Authorization: Bearer ${BUYER_TOKEN}")
echo "${BATCH}"
if [ "${BATCH##*HTTP:}" != "200" ]; then
  echo "GET checkout batch failed" >&2
  exit 1
fi

echo "=== batch-pay ==="
BATCH_PAY=$(curl -sS -w "\nHTTP:%{http_code}" -X POST http://127.0.0.1:8000/orders/batch-pay \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BUYER_TOKEN}" \
  -d "{\"order_ids\":[\"${ORDER_ID}\"]}")
echo "${BATCH_PAY}"
BATCH_PAY_BODY="${BATCH_PAY%HTTP:*}"
if [ "${BATCH_PAY##*HTTP:}" != "200" ]; then
  echo "batch-pay failed" >&2
  exit 1
fi
PAID_STATUS=$(printf '%s' "${BATCH_PAY_BODY}" | python3 -c "import json,sys; print(json.load(sys.stdin)['orders'][0]['status'])")
if [ "${PAID_STATUS}" != "confirmed" ]; then
  echo "expected confirmed after batch-pay, got ${PAID_STATUS}" >&2
  exit 1
fi

echo "=== cart curl smoke passed: add → cart → checkout → batch-pay ==="
