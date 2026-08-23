#!/usr/bin/env bash
# 三库监督器共享逻辑：
#   数据统一根 db-data/、确保 process-compose 监督器（单例）、带名 start/stop。
#   被 scripts/devbox/ 下脚本通过 source 引入；脚本一律经 `devbox run -- task ...` 执行。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ---------------------------------------------------------------------------
# 数据统一根（db-data/，见 .gitignore）
# ---------------------------------------------------------------------------
DB_DATA_ROOT="${PROJECT_ROOT}/db-data"
MYSQL_DATADIR_ABS="${DB_DATA_ROOT}/mysql"
PG_DATA_DIR_ABS="${DB_DATA_ROOT}/postgres/data"
PG_SOCK_DIR_ABS="${DB_DATA_ROOT}/postgres/run"
REDIS_DIR_ABS="${DB_DATA_ROOT}/redis"
MYSQL_INIT_LOG="${PROJECT_ROOT}/.devbox/virtenv/mysql80/run/mysql-init.log"

# ---------------------------------------------------------------------------
# 监督器（process-compose 单例）
# ---------------------------------------------------------------------------
# process-compose 未运行时 pcport 报错退出；用它判别监督器是否已存在
is_supervisor_running() {
  devbox services pcport >/dev/null 2>&1
}

# 确保三个数据目录就绪后再启动监督器：
#   未运行 -> 一次点齐 `up mysql redis postgresql -b`；
#   已运行 -> 跳过（`up <单名>` 在监督器已存在时不能追加）。
ensure_supervisor() {
  ensure_mysql_datadir
  ensure_pg_datadir
  ensure_redis_dir
  if is_supervisor_running; then
    return 0
  fi
  echo "启动监督器（process-compose: mysql redis postgresql）..."
  devbox services up mysql redis postgresql -b
}

# 启用本库进程（已 Running 则忽略，不重启）
start_service() {
  devbox services start "$1" >/dev/null 2>&1 || true
}

# 停止本库进程（带名；绝不无名字 `services stop`，以免拆掉整只监督器）
stop_service() {
  devbox services stop "$1" >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# 各库数据目录初始化（幂等）
# ---------------------------------------------------------------------------
ensure_mysql_datadir() {
  if [ -f "${MYSQL_DATADIR_ABS}/ibdata1" ] || [ -d "${MYSQL_DATADIR_ABS}/mysql" ]; then
    return 0
  fi
  echo "初始化 MySQL 数据目录: ${MYSQL_DATADIR_ABS}"
  rm -rf "${MYSQL_DATADIR_ABS}"
  mkdir -p "${MYSQL_DATADIR_ABS}"
  mkdir -p "$(dirname "${MYSQL_INIT_LOG}")"
  mysqld --initialize-insecure \
    --basedir="${MYSQL_BASEDIR}" \
    --datadir="${MYSQL_DATADIR_ABS}" >>"${MYSQL_INIT_LOG}" 2>&1
  echo "MySQL 数据目录初始化完成（日志: ${MYSQL_INIT_LOG}）"
}

ensure_pg_datadir() {
  mkdir -p "${PG_SOCK_DIR_ABS}"
  if [ -f "${PG_DATA_DIR_ABS}/PG_VERSION" ]; then
    return 0
  fi
  echo "初始化 PostgreSQL 数据目录: ${PG_DATA_DIR_ABS}"
  rm -rf "${PG_DATA_DIR_ABS}"
  mkdir -p "${PG_DATA_DIR_ABS}"
  initdb -D "${PG_DATA_DIR_ABS}" -U "${PG_SUPERUSER:-${USER:-postgres}}" \
    --auth-local=trust --auth-host=scram-sha-256
  {
    echo "listen_addresses = '127.0.0.1'"
    echo "port = ${PGPORT:-5433}"
    echo "unix_socket_directories = '${PG_SOCK_DIR_ABS}'"
  } >>"${PG_DATA_DIR_ABS}/postgresql.conf"
}

ensure_redis_dir() {
  mkdir -p "${REDIS_DIR_ABS}"
}
