#!/usr/bin/env bash
# task redis:down 入口：停止 Redis 服务（带名，不拆整只监督器）
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/services.sh"

if is_supervisor_running; then
  stop_service redis
fi
echo "Redis 服务已停止"
