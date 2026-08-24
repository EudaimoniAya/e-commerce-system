#!/usr/bin/env bash
# task pg:reset 入口：停止 PostgreSQL → 清除 db-data/postgres → 重新启动（开发用，慎用）
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/pg_down.sh"
rm -rf "${DB_DATA_ROOT}/postgres"
bash "${SCRIPT_DIR}/pg_up.sh"
