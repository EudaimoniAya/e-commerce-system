## Why

本地三库监督方式不对称：MySQL/Redis 走 process-compose，PostgreSQL 走 `pg_ctl`；数据目录散落在 `mysql-data/`、`postgres-data/`、`.devbox/virtenv/redis/`。`task ci` 并行 `db:up` + `redis:up` + `pg:up` 会抢 **同一只** process-compose（`services up <单名>` 不能追加）。`db:*` 名义上是总闸，实际只动 MySQL。现在要把 PG 纳入监督器、数据收到 `db-data/`，并一次消掉竞态。

## What Changes

- **一只监督器**：`devbox services up mysql redis postgresql -b`；分库脚本只 `start` 自己。修正 `PGHOST` 为 unix socket **目录**（插件 `postgres -k`），应用仍连 `127.0.0.1:5433`。
- **`db-data/` 统一根**（gitignore）：`mysql/`、`redis/`、`postgres/{data,run}`。本机无旧数据，不写迁移；旧路径名留在 gitignore 防残留。
- **BREAKING Task 语义**：`db:up` / `db:down` / `db:reset` = 三库总闸（reset 清空整个 `db-data/`）。分库：`mysql|redis|pg` 各 `up` / `down` / `reset`。`ci` / `dev` / `test:reports` 只 deps **`db:up`**。`migrate` deps **`mysql:up`**；`migrate:ai` 仍 `pg:up`。
- **竞态写进 ADR-002**（增补，不另开 ADR）：禁止并行各 `up` 一个服务；总闸一次点齐三名；分库 `down` 禁止无名字 `services stop`。
- **readiness 测例收口**：删叠测（多条 200、mysql+redis 双挂、三库全挂）；留单点 503 + 一条真连 200。主 spec 去掉「全部不可用」场景。
- 文档：README、architecture、`.cursor/rules`、`CLAUDE.md`、`openspec/config.yaml` 中「`db:up` = MySQL」全部改掉。

## Non-goals

- **不** 改 CI workflow（仍用 service container，不读 `db-data/`）
- **不** 改业务 API、readiness 路由语义（仍三键 AND）
- **不** 开 Redis AOF、不把 media 存储并进 `db-data/`
- **不** 自动迁移旧 `mysql-data/` / `postgres-data/`
- **不** 为 Taskfile 新写 pytest；**不** 动业务域

## Capabilities

### New Capabilities

- `infra-devbox-services`：本地一只 process-compose、`db-data/` 布局、Task 总闸/分库、监督器竞态纪律

### Modified Capabilities

- `infra-ci`：`task ci` / `dev` / `test:reports` 的 devbox deps **SHALL** 仅为聚合 `db:up`；`task test` 仍无 devbox deps
- `infra-readiness`：去掉「三库同时不可用」场景；保留三库均 ok 与各单点不可用
- `infra-ai-pgvector`：`pg:up` / `pg:down` 仍在，本地启停改为 **devbox postgresql 插件服务**（不再 `pg_ctl` 旁路）

## Impact

- **业务域**：仅 **infra**（本地脚本 / Task / 文档 / readiness 测例）；无 router/service 行为变更
- **文件**：`devbox.json`、`devbox.d/{mysql80,redis}/`、`scripts/devbox_*.sh`、`Taskfile.yml`、`.gitignore`、`tests/ops/test_readiness.py`、`docs/decision/ADR-002-*.md`、README / architecture / rules
- **API**：无
- **短标签**：`[devbox-services]`
- **分支建议**：`feature/infra-devbox-services`
