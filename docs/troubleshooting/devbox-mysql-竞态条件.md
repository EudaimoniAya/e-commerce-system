# devbox MySQL 服务启动竞态条件

## 场景

`task db:up` 负责启动 devbox MySQL 并确保 `ecommerce_dev` / `ecommerce_test` 双库存在。

## 问题

早期实现中：

```text
devbox services up mysql -b   ← 成功返回
mysql -e "CREATE DATABASE ..." ← ERROR 2002: socket 不存在
```

## 根因

`devbox services up mysql -b` 使用 process-compose 启动 MySQL。process-compose 在 mysqld fork 成功后即返回，不等 MySQL 完成内部初始化（InnoDB 恢复、创建 socket 等）。这就是**竞态条件**。

另有 **process-compose 僵死**：process-compose 在跑但 mysqld 已挂，此时重复 `services up` 会报 `already running`，`services stop mysql` 也无法关掉 process-compose。

另有 **mysqld 残留**：仅 `devbox services stop` 可能未关掉 mysqld，导致 `db:down` 后 `db:up` 误判已就绪。

## 解决

逻辑合并到单一入口 `scripts/devbox/mysql_up.sh`（五段）：

1. **数据目录** — 首次或损坏时 `mysqld --initialize-insecure`（日志写入 `mysql-init.log`，不刷屏）
2. **快速路径** — 已就绪则仅输出数据目录与已有库，然后退出
3. **服务启动** — 否则 `devbox services stop` 后 `up mysql -b`（stdout 重定向）
4. **就绪轮询** — 每 1 秒 `mysqladmin ping`（完全静默），最多 60 秒
5. **建库** — `CREATE DATABASE IF NOT EXISTS` dev/test 双库

轮询核心：

```bash
mysqladmin -u root --socket="$SOCKET" ping --silent >/dev/null 2>&1
```

停止服务使用 `scripts/devbox/mysql_down.sh`：先 `mysqladmin shutdown`（socket），再 `devbox services stop` 关掉 process-compose。

重置使用 `scripts/devbox/mysql_reset.sh`：`down` → 删除 `mysql-data/` → `up`（避免 Taskfile 嵌套 task 的冗余输出）。

## 验证

**MySQL 已运行（`task db:up`）：**

```text
MySQL 数据目录: /path/to/mysql-data
已有库: ecommerce_dev, ecommerce_test
```

**需启动或 `task db:reset`：**

```text
MySQL 服务已停止
初始化 MySQL 数据目录: /path/to/mysql-data
MySQL 数据目录初始化完成（日志: .devbox/virtenv/mysql80/run/mysql-init.log）
启动 MySQL...
MySQL 已就绪；数据目录: /path/to/mysql-data；已有库: ecommerce_dev, ecommerce_test
```

## 关键概念

- **process-compose**：devbox 进程管理器；检查进程存活，不保证服务就绪
- **`-b`**：后台模式；不加则 process-compose 占住终端
- **`mysqladmin ping`**：MySQL 就绪的真实信号（socket 可连）
- **`mysqladmin shutdown`**：`db:down` 时通过 socket 优雅关闭，避免残留进程

## 关联文件

- `Taskfile.yml` — `db:up` / `db:down` / `db:reset`
- `scripts/devbox/mysql_up.sh` — 启动全流程（初始化 + up + 轮询 + 建库）
- `scripts/devbox/mysql_down.sh` — socket shutdown + 停止 process-compose
- `scripts/devbox/mysql_reset.sh` — 重置全流程
- `.cursor/rules/service-startup-readiness-polling.mdc` — 通用轮询模式规则
- `.devbox/virtenv/mysql80/process-compose.yaml` — process-compose 服务定义
