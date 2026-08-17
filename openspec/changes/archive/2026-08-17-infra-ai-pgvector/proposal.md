## Why

AI 读副本依赖 **PostgreSQL + pgvector**，但仓库尚无 AI 库连接、第二 Alembic 入口、Embedding 抽象与 readiness 探测；本地 `task ci` / `task dev` 也未统一拉起 MySQL/Redis（及即将需要的 PG）服务。在后续 RAG 索引与 `ai-support-agent` change 之前，须先交付 **可演示的 pgvector 基础设施**，并顺带收编 Task/CI/文档层面的服务依赖纪律。

## What Changes

- 在 **devbox** 引入 **PostgreSQL（含 pgvector）**，提供 `task pg:up` / `task pg:down` 及就绪轮询脚本（镜像 `devbox_redis_up.sh` 模式）
- 在 **`Settings`** 新增必填 **`AI_DATABASE_URL`** 与 **Embedding 配置**（`EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSION` 等）；CI 默认 `mock` provider
- 新增 **`app/infra/ai_database.py`**：`AiBase`、async PG engine/session、`get_ai_engine()` / `reset_ai_engine()`（镜像 `database.py` 模式）
- 新增 **`app/infra/embedder.py`**：`Embedder` 协议、`MockEmbedder`、厂商 API 实现骨架、`get_embedder()`；**启动时维度校验**（配置维度须与 Embedder 及 migration 一致）
- 新增 **`alembic_ai/`** 第二迁移入口；首条 revision：`CREATE EXTENSION vector` + infra 验证表 `_infra_ai_migration_smoke`（含 `vector(N)` 列）
- 扩展 **`GET /health/ready`**：`checks` 增加 **`postgresql`**，与 `mysql`、`redis` 并列；三者均 ok 时 `status=ready`
- 在 **CI**（`.github/workflows/test.yaml`）增加 **`services.postgres`**（pgvector 镜像 + healthcheck）、`AI_DATABASE_URL` 与 migrate 步骤；**仍** 通过 `task test` 跑 pytest（不加 devbox deps）
- **Taskfile 服务依赖收编**：
  - `task ci.deps` → `db:up` + `redis:up` + `pg:up`；`ci` 在 `test` 前执行 `migrate` + `migrate:ai`
  - `task dev.deps` → `db:up` + `redis:up`
  - `task migrate.deps` → `db:up`；新增 `task migrate:ai`（deps `pg:up`）、`task migrate:all`
  - `task test` **保持无** devbox deps（供 CI）；`task test:reports.deps` 增加 `pg:up`
- 新增 **integration 测试**：AI migration smoke、Embedder 维度、PG 向量 CRUD smoke、readiness 含 postgresql
- 更新 **`.env.example`**、**`README.md`**、**`docs/architecture.md`**、**`docs/decision/ADR-002-测试与数据库策略.md`**（PostgreSQL/pgvector 与 Task 约定）、**`openspec/config.yaml`**、**`pyproject.toml`** markers
- 在 **`pyproject.toml`** 增加 **`asyncpg`**、**`pgvector`** 依赖

## Non-goals

- **不** 实现商品索引、领域事件、`events/`、`ai/indexing`（留给 `ai-rag-acl-index` change）
- **不** 实现 support RAG、`append_ai_reply`、`handler_mode` AI 路由（留给 `ai-support-agent` change）
- **不** 引入 Celery、Outbox、LangChain / LangGraph
- **不** 新增 `product_embedding_chunks` 等业务向量表（Change 2 migration）
- **不** 在 CI 调用真 Embedding 厂商 API（CI 使用 `MockEmbedder`）
- **不** 修改 user / catalog / ordering / engagement / support / media **业务 API 或行为**
- **不** 本地 docker-compose 提供 PostgreSQL（与 MySQL/Redis ADR 一致，本地用 devbox services）
- **不** 引入 PG 主从、连接池生产调优、Terraform/K8s（留给部署 change）

## Capabilities

### New Capabilities

- `infra-ai-pgvector`: PostgreSQL + pgvector 配置、`AI_DATABASE_URL`、async 客户端、第二 Alembic 入口、`Embedder` 抽象与维度校验、devbox/CI 提供方式、dev/test 双库约定、向量 smoke 演示

### Modified Capabilities

- `infra-readiness`: 聚合 readiness 在 MySQL、Redis 之外 **SHALL** 检查 PostgreSQL；`checks` 含 `postgresql` 键；三依赖均可用时返回 ready
- `infra-ci`: test job **SHALL** 声明 postgres service container；**SHALL** 在 pytest 前执行 AI 库 migrate；本地 `task ci` **SHALL** 通过 deps 确保三库就绪并在 test 前 migrate

## Impact

- **业务域**: 仅 **infra**（config、ai_database、embedder、readiness、models）；无业务域 router/service 变更
- **新增/修改文件**: `devbox.json`、`scripts/devbox_pg_*.sh`、`Taskfile.yml`、`alembic_ai/`、`app/infra/ai_database.py`、`app/infra/embedder.py`、`app/infra/models/`、`app/infra/readiness/`、`.github/workflows/test.yaml`、`.env.example`、`tests/infra/`、`tests/ops/`、`pyproject.toml`、`docs/`、`openspec/config.yaml`
- **API**: `GET /health/ready` 响应 `checks` 增加 `postgresql`；无业务 REST 变更
- **依赖**: `asyncpg`、`pgvector`（SQLAlchemy 集成）
- **环境**: 本地 integration / `task ci` 前须三库就绪（`task ci` deps 自动处理）；CI 由 workflow `services` + healthcheck 提供；`task test` 仍假设环境已由 workflow 或调用方准备好
