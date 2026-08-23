#!/usr/bin/env bash
# task db:up 入口：三库总闸。
#   依次调用 mysql/redis/pg 三个分库 up（各自内部 ensure_supervisor 只触发一次真实的
#   `services up mysql redis postgresql`，后续跳过）；禁止并行各 up，避免抢同一只监督器。
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

bash "${SCRIPT_DIR}/mysql_up.sh"
bash "${SCRIPT_DIR}/redis_up.sh"
bash "${SCRIPT_DIR}/pg_up.sh"
echo "三库均已就绪：MySQL / Redis / PostgreSQL"
