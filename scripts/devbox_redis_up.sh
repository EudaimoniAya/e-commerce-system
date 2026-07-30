#!/usr/bin/env bash
# task redis:up 入口：启动 devbox Redis → 轮询就绪 → 输出摘要
set -euo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WAIT_TIMEOUT_SEC=30

cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
is_redis_ready() {
  redis-cli ping | grep -q PONG
}

print_summary() {
  local port="${REDIS_PORT:-6379}"
  echo "Redis 已就绪；端口: ${port}；逻辑库: 0（dev）/ 1（test）"
}

# ---------------------------------------------------------------------------
# 1. 已就绪：仅输出摘要
# ---------------------------------------------------------------------------
if is_redis_ready; then
  print_summary
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. 服务启动
# ---------------------------------------------------------------------------
ensure_redis_service_started() {
  # process-compose 未运行时，可单独 up redis
  if devbox services up redis -b -q 2>/dev/null; then
    return 0
  fi

  # db:up 已占用 process-compose 时，redis 在 compose 内为 Disabled，
  # 此时 devbox 报 "process-compose is already running" 且无法单独启用 redis。
  if devbox services ls 2>/dev/null | grep -qE 'mysql[[:space:]]+default[[:space:]]+Running'; then
    echo "process-compose 已运行 MySQL，重启 mysql+redis..."
    local socket="${MYSQL_UNIX_PORT:-/tmp/e-commerce-system-mysql.sock}"
    mysqladmin -u root --socket="${socket}" shutdown >/dev/null 2>&1 || true
    redis-cli shutdown nosave >/dev/null 2>&1 || true
    devbox services stop -q 2>/dev/null || true
    sleep 1
    if devbox services up mysql redis -b -q 2>/dev/null; then
      return 0
    fi
  fi

  echo "启动 Redis 失败。可手动执行:" >&2
  echo "  devbox services stop && devbox services up mysql redis -b" >&2
  return 1
}

echo "启动 Redis..."
ensure_redis_service_started

# ---------------------------------------------------------------------------
# 3. 就绪轮询（进程已启动 ≠ 服务已就绪）
# ---------------------------------------------------------------------------
for i in $(seq 1 "${WAIT_TIMEOUT_SEC}"); do
  if is_redis_ready; then
    break
  fi
  if [ "${i}" -eq "${WAIT_TIMEOUT_SEC}" ]; then
    echo "Redis 在 ${WAIT_TIMEOUT_SEC} 秒内未就绪，请查看 .devbox/virtenv/redis/redis.log" >&2
    exit 1
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 4. 输出摘要
# ---------------------------------------------------------------------------
print_summary
