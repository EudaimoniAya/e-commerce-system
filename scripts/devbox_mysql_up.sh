#!/usr/bin/env bash
# task db:up 入口：初始化数据目录 → 启动 devbox MySQL → 轮询就绪 → 创建 dev/test 双库
set -euo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATADIR="${PROJECT_ROOT}/mysql-data"
SOCKET="${MYSQL_UNIX_PORT:-/tmp/e-commerce-system-mysql.sock}"
WAIT_TIMEOUT_SEC=60
INIT_LOG="${PROJECT_ROOT}/.devbox/virtenv/mysql80/run/mysql-init.log"

cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
is_mysql_ready() {
  mysqladmin -u root --socket="${SOCKET}" ping --silent >/dev/null 2>&1
}

is_valid_datadir() {
  [ -f "${DATADIR}/ibdata1" ] || [ -d "${DATADIR}/mysql" ]
}

print_datadir() {
  echo "MySQL 数据目录: ${DATADIR}"
}

list_target_dbs() {
  mysql -u root --socket="${SOCKET}" -N -e "
    SELECT GROUP_CONCAT(schema_name ORDER BY schema_name SEPARATOR ', ')
    FROM information_schema.schemata
    WHERE schema_name IN ('ecommerce_dev', 'ecommerce_test');
  "
}

print_db_info() {
  local dbs
  dbs="$(list_target_dbs)"
  echo "已有库: ${dbs:-（无）}"
}

print_summary() {
  local dbs
  dbs="$(list_target_dbs)"
  echo "MySQL 已就绪；数据目录: ${DATADIR}；已有库: ${dbs:-（无）}"
}

ensure_databases() {
  mysql -u root --socket="${SOCKET}" -e "
    CREATE DATABASE IF NOT EXISTS ecommerce_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    CREATE DATABASE IF NOT EXISTS ecommerce_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  "
}

# ---------------------------------------------------------------------------
# 1. 数据目录初始化（首次或损坏时执行 mysqld --initialize-insecure）
# ---------------------------------------------------------------------------
if ! is_valid_datadir; then
  echo "初始化 MySQL 数据目录: ${DATADIR}"
  rm -rf "${DATADIR}"
  mkdir -p "${DATADIR}"
  mkdir -p "$(dirname "${SOCKET}")"
  mkdir -p "$(dirname "${INIT_LOG}")"
  mysqld --initialize-insecure \
    --basedir="${MYSQL_BASEDIR}" \
    --datadir="${DATADIR}" >>"${INIT_LOG}" 2>&1
  echo "MySQL 数据目录初始化完成（日志: ${INIT_LOG}）"
fi

# ---------------------------------------------------------------------------
# 2. 已就绪：仅输出数据目录与库信息
# ---------------------------------------------------------------------------
if is_mysql_ready; then
  print_datadir
  ensure_databases
  print_db_info
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. 服务启动
# ---------------------------------------------------------------------------
echo "启动 MySQL..."
devbox services up mysql -b -q >/dev/null 2>&1

# ---------------------------------------------------------------------------
# 4. 就绪轮询（进程已启动 ≠ 服务已就绪，见 .cursor/rules/service-startup-readiness-polling.mdc）
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
# 5. 创建 dev/test 双库并输出摘要
# ---------------------------------------------------------------------------
ensure_databases
print_summary
