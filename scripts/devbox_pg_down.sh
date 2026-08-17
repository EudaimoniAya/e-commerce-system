#!/usr/bin/env bash
# 停止本项目 PostgreSQL 实例（pg_ctl）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATADIR="${PGDATA:-${PROJECT_ROOT}/postgres-data}"
DATADIR="$(cd "${PROJECT_ROOT}" && realpath -m "${DATADIR}")"

if pg_ctl -D "${DATADIR}" status >/dev/null 2>&1; then
  pg_ctl -D "${DATADIR}" -m fast stop
  echo "PostgreSQL 服务已停止"
else
  echo "PostgreSQL 未运行（PGDATA: ${DATADIR}）"
fi
