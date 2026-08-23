#!/usr/bin/env bash
# task mysql:reset 入口：停止 MySQL → 清除 db-data/mysql → 重新启动（开发用，慎用）
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/mysql_down.sh"
rm -rf "${MYSQL_DATADIR_ABS}"
bash "${SCRIPT_DIR}/mysql_up.sh"
