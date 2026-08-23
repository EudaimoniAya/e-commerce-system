#!/usr/bin/env bash
# task redis:reset 入口：停止 Redis → 清除 db-data/redis → 重新启动（开发用，慎用）
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/redis_down.sh"
rm -rf "${REDIS_DIR_ABS}"
bash "${SCRIPT_DIR}/redis_up.sh"
