## ADDED Requirements

### Requirement: Single process-compose for local datastores

本地 MySQL、Redis 与 PostgreSQL SHALL 由 **同一只** process-compose 监督。冷启动 SHALL 执行一次 `devbox services up mysql redis postgresql`（可带 `-b`）。监督器已运行时，分库启动 SHALL 使用 `devbox services start <名>`，SHALL NOT 再执行针对单名的 `devbox services up <单名>`。

#### Scenario: 总闸一次点齐三名

- **WHEN** 开发者执行 `devbox run -- task db:up` 且监督器未运行
- **THEN** 启动命令 SHALL 同时点名 `mysql`、`redis` 与 `postgresql`
- **AND** MySQL、Redis、PostgreSQL 均 SHALL 在超时内就绪（各自探测：`mysqladmin ping` / `redis-cli ping` / `pg_isready`）

#### Scenario: 分库在监督器已存在时只 start

- **WHEN** 监督器已在跑且开发者执行 `devbox run -- task redis:up`（或 `mysql:up` / `pg:up`）
- **THEN** 脚本 SHALL NOT 因 `process-compose is already running` 失败
- **AND** SHALL 通过 `services start` 启用对应进程（若尚未 Running）

### Requirement: Unified db-data directory

本地三库数据 SHALL 落在项目根 `db-data/` 下：`mysql/`、`redis/`、`postgres/data`（PGDATA）、`postgres/run`（`PGHOST` unix socket 目录）。`PGHOST` SHALL 为目录路径，SHALL NOT 为 `127.0.0.1`。应用 AI 库连接 SHALL 仍使用 TCP `127.0.0.1` 与 `PGPORT`（本地默认 5433）。`db-data/` SHALL 被 gitignore。

#### Scenario: 配置指向 db-data 且 PGHOST 非 IP

- **WHEN** 检查 `devbox.json` 与 Redis/MySQL 本地配置
- **THEN** 数据路径 SHALL 包含 `db-data`
- **AND** `PGHOST` SHALL NOT 等于 `127.0.0.1`

### Requirement: Task taxonomy for aggregate and per-engine

Taskfile SHALL 提供聚合任务 `db:up`、`db:down`、`db:reset` 与分库任务 `mysql|redis|pg` 的 `up` / `down` / `reset`。`db:reset` SHALL 停止三库并删除整个 `db-data/` 后再次 `db:up`。分库 `down` SHALL 调用 `devbox services stop <该服务名>`，SHALL NOT 使用无名字的 `devbox services stop`。

#### Scenario: db reset 清空统一根

- **WHEN** 开发者执行 `devbox run -- task db:reset`
- **THEN** `db-data/` SHALL 在重启后为新初始化的数据根（旧 cluster/RDB 不保留）

#### Scenario: 分库 down 不拆整只监督器

- **WHEN** 三库均在跑且开发者执行 `devbox run -- task redis:down`
- **THEN** Redis SHALL 停止
- **AND** MySQL 与 PostgreSQL SHALL 仍可继续运行（监督器不因此被拆除）
