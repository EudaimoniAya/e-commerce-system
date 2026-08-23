#!/usr/bin/env bash
# task pg:up 入口：确保监督器与数据目录（initdb）→ 启用 postgresql 插件服务 → pg_isready → 建 AI 双库 + pgvector
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

cd "${PROJECT_ROOT}"

PGPORT="${PGPORT:-5433}"
SUPERUSER="${PG_SUPERUSER:-${USER:-postgres}}"
WAIT_TIMEOUT_SEC=60

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
is_pg_ready() {
  pg_isready -h 127.0.0.1 -p "${PGPORT}" -U "${SUPERUSER}" >/dev/null 2>&1
}

admin_psql() {
  # 走 PGHOST socket 目录（auth-local=trust）；TCP 需密码故不走 127.0.0.1
  PGHOST="${PG_SOCK_DIR_ABS}" PGPORT="${PGPORT}" psql -U "${SUPERUSER}" -d postgres "$@"
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
  echo "PostgreSQL 已就绪；PGDATA: ${PG_DATA_DIR_ABS}；端口: ${PGPORT}；已有 AI 库: ${dbs:-（无）}"
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

# ---------------------------------------------------------------------------
# 1. 确保监督器（含 initdb 与 socket 目录创建）
# ---------------------------------------------------------------------------
ensure_supervisor

# ---------------------------------------------------------------------------
# 2. 已就绪：仅建库并输出摘要
# ---------------------------------------------------------------------------
if is_pg_ready; then
  ensure_role_postgres
  ensure_databases
  print_summary
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. 启用本库进程（不再 pg_ctl start；由监督器统一监督）
# ---------------------------------------------------------------------------
start_service postgresql

# ---------------------------------------------------------------------------
# 4. 就绪轮询（pg_isready 必须带 -h 127.0.0.1 -p ${PGPORT}）
# ---------------------------------------------------------------------------
for i in $(seq 1 "${WAIT_TIMEOUT_SEC}"); do
  if is_pg_ready; then
    break
  fi
  if [ "${i}" -eq "${WAIT_TIMEOUT_SEC}" ]; then
    echo "PostgreSQL 在 ${WAIT_TIMEOUT_SEC} 秒内未就绪，请查看 ${PG_DATA_DIR_ABS}/postgresql.log" >&2
    exit 1
  fi
  sleep 1
done

# ---------------------------------------------------------------------------
# 5. 创建 AI 双库、pgvector 扩展并输出摘要
# ---------------------------------------------------------------------------
ensure_role_postgres
ensure_databases
print_summary
