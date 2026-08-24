# infra-ai-pgvector Specification

## Purpose
TBD - created by archiving change infra-ai-pgvector. Update Purpose after archive.
## Requirements
### Requirement: AI database URL configuration

系统 SHALL 通过 `pydantic-settings` 从环境变量加载必填配置 `AI_DATABASE_URL`（PostgreSQL 异步连接 URI，使用 `postgresql+asyncpg` 驱动）。配置不得硬编码于业务代码。

#### Scenario: 缺少 AI_DATABASE_URL 时应用启动失败

- **WHEN** 未设置 `AI_DATABASE_URL` 且应用工厂或 Settings 初始化需要 AI 库配置
- **THEN** 系统 SHALL 以明确校验错误失败，而非静默使用默认 localhost

#### Scenario: AI_DATABASE_URL 指向有效 PostgreSQL 实例

- **WHEN** `AI_DATABASE_URL` 设置为可连接的 PostgreSQL URI
- **THEN** infra AI 数据库客户端 SHALL 使用该 URL 建立连接

### Requirement: Dev and test AI database separation

系统 SHALL 约定：本地开发默认使用数据库 **`ecommerce_ai_dev`**；pytest integration 与 CI SHALL 使用 **`ecommerce_ai_test`**，以避免测试数据污染开发环境。

#### Scenario: 测试环境使用 ecommerce_ai_test

- **WHEN** pytest integration 测试或 CI job 运行且加载 `.env.test` 或 workflow 注入的 `AI_DATABASE_URL`
- **THEN** 连接串 SHALL 指向数据库名 `ecommerce_ai_test`

#### Scenario: 开发环境使用 ecommerce_ai_dev

- **WHEN** 本地开发加载默认 `.env` 示例配置
- **THEN** 文档或 `.env.example` SHALL 示例 `AI_DATABASE_URL` 使用数据库名 `ecommerce_ai_dev`

### Requirement: Separate ORM base and Alembic entry for AI database

系统 SHALL 为 PostgreSQL AI 库提供独立于 MySQL 的 ORM 基类 `AiBase`（`app/infra/ai_database.py`）与 Alembic 配置入口 `alembic_ai/`（`alembic_ai.ini`）。MySQL 的 `alembic/` 入口 SHALL NOT 管理 AI 库 schema。

#### Scenario: AI Alembic upgrade head 创建 pgvector 扩展

- **WHEN** 开发者在 AI 库上执行 `alembic -c alembic_ai.ini upgrade head`（或 `task migrate:ai`）
- **THEN** 数据库 SHALL 存在 PostgreSQL 扩展 `vector`

#### Scenario: MySQL migrate 不影响 AI 库

- **WHEN** 开发者仅执行 `task migrate`（MySQL `alembic upgrade head`）
- **THEN** AI 库 schema SHALL 不被 MySQL Alembic 修改

### Requirement: Async PostgreSQL client in infra

系统 SHALL 在 `app/infra/ai_database.py` 提供基于 SQLAlchemy 2 async（`asyncpg`）的共享 engine/session 工厂及 `reset_ai_engine()`（测试隔离）。业务域与未来 `ai/` 模块 SHALL 通过 infra 暴露的 API 访问 AI 库，**仅 infra 模块** 持有 AI 库 `create_async_engine` 与连接池生命周期。

#### Scenario: integration 测试连接 AI 库成功

- **WHEN** integration 测试通过 infra 提供的 session 执行 `SELECT 1`
- **THEN** 查询 SHALL 成功

#### Scenario: reset_ai_engine 供 integration 隔离

- **WHEN** integration 测试 autouse fixture 在前后调用 `reset_ai_engine()`
- **THEN** SHALL 不引发跨事件循环连接池冲突（与 `reset_engine` 纪律一致）

### Requirement: Infra AI migration smoke table

系统 SHALL 在 `alembic_ai/` 首条 revision 创建 infra 验证表 `_infra_ai_migration_smoke`（非业务域表），含 `vector(N)` 列，其中 **N SHALL 等于** 配置的 `EMBEDDING_DIMENSION`（本 change migration 001 采用 **1024**；Settings 仍须显式配置，无 default）。

#### Scenario: upgrade head 后 smoke 表存在

- **WHEN** 执行 AI 库 `upgrade head`
- **THEN** 数据库 SHALL 存在表 `_infra_ai_migration_smoke`
- **AND** 其 `embedding` 列 SHALL 为 `vector(1024)`（当 `EMBEDDING_DIMENSION=1024`）

#### Scenario: smoke 表 CRUD 与向量写入

- **WHEN** integration 测试在 transaction 内向 `_infra_ai_migration_smoke` 插入含 embedding 的行并做相似度查询
- **THEN** SHALL 读回或检索到写入的数据

### Requirement: Embedder abstraction and dimension validation

系统 SHALL 在 `app/infra/embedder.py` 提供 `Embedder` 协议（含 `dimension` 属性与 `embed_texts` 方法）、`get_embedder()` 工厂及 **`MockEmbedder`**（CI 与默认测试使用）。系统 SHALL 在应用启动时校验 **`get_embedder().dimension == settings.embedding_dimension`**，不一致时 **SHALL** fail-fast。向量写入前 SHALL 校验向量长度等于 `dimension`。

#### Scenario: MockEmbedder 返回配置维度

- **WHEN** `EMBEDDING_PROVIDER=mock` 且 `EMBEDDING_DIMENSION=1024`
- **THEN** `get_embedder().embed_texts(["测试"])` SHALL 返回长度为 1 的列表，且每个向量长度为 1024

#### Scenario: 配置维度与 Embedder 不一致时启动失败

- **WHEN** `EMBEDDING_DIMENSION` 与 `get_embedder().dimension` 不一致
- **THEN** 应用启动或 embedder 初始化 SHALL 失败并给出明确错误信息

#### Scenario: CI 使用 mock provider

- **WHEN** CI workflow 设置 `EMBEDDING_PROVIDER=mock`
- **THEN** integration 测试 SHALL NOT 调用外部 Embedding HTTP API

### Requirement: Embedding settings

系统 SHALL 通过 Settings 加载 `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSION`（**必填整数，无 pydantic default**）及可选 `EMBEDDING_API_KEY`。`.env.example` 与 CI workflow SHALL 提供示例值 `1024`。文档 SHALL 说明 LLM 对话与 Embedding 厂商可分离（如 DeepSeek 无 embedding API 时 embedding 须另配）。

#### Scenario: EMBEDDING_DIMENSION 缺失时校验失败

- **WHEN** 未设置 `EMBEDDING_DIMENSION`
- **THEN** Settings 初始化 SHALL 失败

### Requirement: Local PostgreSQL via devbox

系统 SHALL 通过 **devbox postgresql 插件服务**（process-compose 进程名 `postgresql`）提供本地 PostgreSQL（含 **pgvector**）；SHALL 提供 `task pg:up` 与 `task pg:down` 及就绪轮询（`pg_isready`），并确保 dev/test AI 库存在。`pg:up` SHALL NOT 使用独立于 process-compose 的 `pg_ctl start` 作为主路径。`pg:down` SHALL 使用 `devbox services stop postgresql`。

#### Scenario: pg up 后就绪

- **WHEN** 开发者在项目根目录执行 `devbox run -- task pg:up` 且 PostgreSQL 正常启动
- **THEN** 脚本 SHALL 在超时内检测到 `pg_isready` 成功并输出就绪摘要
- **AND** `postgresql` 进程 SHALL 由 process-compose 监督（`devbox services ls` 为 Running）

#### Scenario: pg down 停止服务

- **WHEN** 三库均在跑且开发者执行 `devbox run -- task pg:down`
- **THEN** PostgreSQL 插件服务 SHALL 停止
- **AND** MySQL 与 Redis SHALL 仍可继续运行

### Requirement: CI PostgreSQL service container

GitHub Actions test workflow SHALL 声明 `services.postgres` 使用 **`pgvector/pgvector:pg16`**（或文档约定的等价 pgvector 镜像），配置 healthcheck（`pg_isready -U postgres`）与端口 `5432`；job 环境 SHALL 设置 `AI_DATABASE_URL` 指向 test AI 库，并在 pytest 前执行 AI 库 migrate。

#### Scenario: CI test job 启动 postgres sidecar

- **WHEN** CI test job 运行且命中 `code` filter
- **THEN** postgres service container SHALL 在 migrate 与 pytest 步骤前通过 healthcheck 就绪

#### Scenario: CI 与本地共用同一套 PG integration 测试

- **WHEN** 同一 PG integration 测试在本地（devbox + `.env.test`）与 CI 中执行
- **THEN** 二者 SHALL 均通过，且均使用 pgvector 扩展

### Requirement: AI database integration tests

系统 SHALL 提供 `@pytest.mark.integration` 标识的 AI 库相关测试，验证配置加载、migration smoke、Embedder 维度与向量 CRUD；数量精简，建议集中在 `tests/infra/test_pg.py`、`tests/infra/test_embedder.py`、`tests/ops/test_ai_migration_smoke.py`。

#### Scenario: integration marker 存在

- **WHEN** 查看上述 AI 相关测试模块
- **THEN** 这些测试 SHALL 带有 `integration` marker

#### Scenario: conftest 提供 AI 库测试隔离

- **WHEN** integration 测试需要 AI 库连接
- **THEN** SHALL 通过 `reset_ai_engine()` autouse 或等价 fixture 避免跨 loop 冲突

### Requirement: Migrate tasks for dual Alembic

Taskfile SHALL 提供 `migrate:ai`（deps `pg:up`，执行 AI Alembic upgrade head）与 `migrate:all`（MySQL + AI 顺序 migrate）。

#### Scenario: migrate:ai 依赖 pg up

- **WHEN** 开发者执行 `devbox run -- task migrate:ai`
- **THEN** Task SHALL 先确保 PostgreSQL 就绪再执行 Alembic

#### Scenario: migrate:all 升级双库

- **WHEN** 开发者执行 `devbox run -- task migrate:all`
- **THEN** SHALL 依次完成 MySQL 与 AI 库 `upgrade head`

