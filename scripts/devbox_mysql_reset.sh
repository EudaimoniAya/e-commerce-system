#!/usr/bin/env bash
# task db:reset 入口：停止 MySQL → 清除 mysql-data/ → 重新启动
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

bash "${SCRIPT_DIR}/devbox_mysql_down.sh"
rm -rf "${PROJECT_ROOT}/mysql-data/"
bash "${SCRIPT_DIR}/devbox_mysql_up.sh"
