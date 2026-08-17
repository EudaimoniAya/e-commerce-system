#!/usr/bin/env bash
# task pg:up 入口：初始化 PGDATA → pg_ctl 启动 → pg_isready 轮询 → 建 AI 双库 + pgvector
set -euo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATADIR="${PGDATA:-${PROJECT_ROOT}/postgres-data}"
PGPORT="${PGPORT:-5432}"
WAIT_TIMEOUT_SEC=60
SUPERUSER="${PG_SUPERUSER:-${USER:-postgres}}"

cd "${PROJECT_ROOT}"
DATADIR="$(cd "${PROJECT_ROOT}" && realpath -m "${DATADIR}")"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
is_our_pg_running() {
  pg_ctl -D "${DATADIR}" status >/dev/null 2>&1
}

is_pg_ready() {
  pg_isready -h 127.0.0.1 -p "${PGPORT}" -U "${SUPERUSER}" >/dev/null 2>&1
}

admin_psql() {
  # 走项目 PGDATA 内 unix socket（auth-local=trust）
  PGHOST="${DATADIR}" psql -U "${SUPERUSER}" -d postgres "$@"
}

list_target_dbs() {
  admin_psql -At -c "
    SELECT string_agg(datname, ', ' ORDER BY datname)
    FROM pg_database
    WHERE datname IN ('ecommerce_ai_dev', 'ecommerce_ai_test');
  "
}

print_summary() {
  local dbs vector_ok
  dbs="$(list_target_dbs)"
  vector_ok="$(admin_psql -At -c \
    "SELECT COUNT(*) FROM pg_available_extensions WHERE name = 'vector';")"
  echo "PostgreSQL 已就绪；PGDATA: ${DATADIR}；端口: ${PGPORT}；已有 AI 库: ${dbs:-（无）}"
  if [ "${vector_ok}" = "0" ]; then
    echo "警告: pgvector 扩展不可用，请确认 devbox 已安装 postgresql16Packages.pgvector" >&2
  fi
}

ensure_role_postgres() {
  admin_psql -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
    CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres';
  ELSE
    ALTER ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres';
  END IF;
END
$$;
SQL
}

ensure_databases() {
  admin_psql -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE DATABASE ecommerce_ai_dev OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ecommerce_ai_dev')\gexec
SELECT 'CREATE DATABASE ecommerce_ai_test OWNER postgres'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ecommerce_ai_test')\gexec
SQL
  for db in ecommerce_ai_dev ecommerce_ai_test; do
    admin_psql -d "${db}" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;"
  done
}

init_datadir_if_needed() {
  if [ -f "${DATADIR}/PG_VERSION" ]; then
    return 0
  fi
  echo "初始化 PostgreSQL 数据目录: ${DATADIR}"
  rm -rf "${DATADIR}"
  mkdir -p "${DATADIR}"
  initdb -D "${DATADIR}" -U "${SUPERUSER}" --auth-local=trust --auth-host=scram-sha-256
  {
    echo "listen_addresses = '127.0.0.1'"
    echo "port = ${PGPORT}"
    echo "unix_socket_directories = '${DATADIR}'"
  } >> "${DATADIR}/postgresql.conf"
}

start_postgres() {
  if is_our_pg_running; then
    return 0
  fi
  echo "启动 PostgreSQL（pg_ctl）..."
  pg_ctl -D "${DATADIR}" -l "${DATADIR}/postgresql.log" -w start
}

# ---------------------------------------------------------------------------
# 1. 数据目录初始化
# ---------------------------------------------------------------------------
init_datadir_if_needed

# ---------------------------------------------------------------------------
# 2. 启动本实例并轮询就绪
# ---------------------------------------------------------------------------
start_postgres

for i in $(seq 1 "${WAIT_TIMEOUT_SEC}"); do
  if is_pg_ready; then
    break
  fi
  if [ "${i}" -eq "${WAIT_TIMEOUT_SEC}" ]; then
    echo "PostgreSQL 在 ${WAIT_TIMEOUT_SEC} 秒内未就绪，请查看 ${DATADIR}/postgresql.log" >&2
    exit 1
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 3. 创建 AI 双库、pgvector 扩展并输出摘要
# ---------------------------------------------------------------------------
ensure_role_postgres
ensure_databases
print_summary
