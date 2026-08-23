#!/usr/bin/env bash
# task db:reset 入口：三库总闸 reset = down + 清空 db-data/ + up（开发用，慎用）
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/db_down.sh"
rm -rf "${DB_DATA_ROOT}"
bash "${SCRIPT_DIR}/db_up.sh"
