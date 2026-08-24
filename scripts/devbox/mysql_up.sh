#!/usr/bin/env bash
# task mysql:up 入口：确保监督器与数据目录 → 启用 MySQL → 轮询就绪 → 创建 dev/test 双库
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

cd "${PROJECT_ROOT}"

SOCKET="${MYSQL_UNIX_PORT:-/tmp/e-commerce-system-mysql.sock}"
WAIT_TIMEOUT_SEC=60

is_mysql_ready() {
  mysqladmin -u root --socket="${SOCKET}" ping --silent >/dev/null 2>&1
}

list_target_dbs() {
  mysql -u root --socket="${SOCKET}" -N -e "
    SELECT GROUP_CONCAT(schema_name ORDER BY schema_name SEPARATOR ', ')
    FROM information_schema.schemata
    WHERE schema_name IN ('ecommerce_dev', 'ecommerce_test');
  "
}

ensure_databases() {
  mysql -u root --socket="${SOCKET}" -e "
    CREATE DATABASE IF NOT EXISTS ecommerce_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    CREATE DATABASE IF NOT EXISTS ecommerce_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  "
}

print_summary() {
  local dbs
  dbs="$(list_target_dbs)"
  echo "MySQL 已就绪；数据目录: ${MYSQL_DATADIR_ABS}；已有库: ${dbs:-（无）}"
}

# ---------------------------------------------------------------------------
# 1. 确保监督器（含 MySQL 数据目录初始化）
# ---------------------------------------------------------------------------
ensure_supervisor

# ---------------------------------------------------------------------------
# 2. 已就绪：仅建库并输出摘要
# ---------------------------------------------------------------------------
if is_mysql_ready; then
  ensure_databases
  print_summary
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. 启用本库进程（监督器内若为 Disabled/已停则 start 拉起）
# ---------------------------------------------------------------------------
start_service mysql

# ---------------------------------------------------------------------------
# 4. 就绪轮询（进程已启动 ≠ 服务已就绪）
# ---------------------------------------------------------------------------
for i in $(seq 1 "${WAIT_TIMEOUT_SEC}"); do
  if is_mysql_ready; then
    break
  fi
  if [ "${i}" -eq "${WAIT_TIMEOUT_SEC}" ]; then
    echo "MySQL 在 ${WAIT_TIMEOUT_SEC} 秒内未就绪，请查看 .devbox/virtenv/mysql80/run/mysql.log" >&2
    exit 1
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 5. 建库并输出摘要
# ---------------------------------------------------------------------------
ensure_databases
print_summary
