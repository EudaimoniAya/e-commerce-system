#!/usr/bin/env bash
# 停止 devbox process-compose（含 MySQL 服务）
set -euo pipefail

SOCKET="${MYSQL_UNIX_PORT:-/tmp/e-commerce-system-mysql.sock}"

# 先尝试通过 socket 优雅关闭 mysqld，避免 process-compose 停止后进程残留
mysqladmin -u root --socket="${SOCKET}" shutdown >/dev/null 2>&1 || true
devbox services stop -q 2>/dev/null || true
echo "MySQL 服务已停止"
