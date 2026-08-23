#!/usr/bin/env bash
# task db:down 入口：三库总闸。依次带名停止 mysql/redis/pg，监督器不拆除。
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/mysql_down.sh"
bash "${SCRIPT_DIR}/redis_down.sh"
bash "${SCRIPT_DIR}/pg_down.sh"
echo "三库均已停止"
