#!/usr/bin/env bash
# 停止 devbox Redis 服务
set -euo pipefail

# 先尝试通过 redis-cli 优雅关闭，避免 process-compose 停止后进程残留
redis-cli shutdown nosave >/dev/null 2>&1 || true
devbox services stop -q 2>/dev/null || true
echo "Redis 服务已停止"
