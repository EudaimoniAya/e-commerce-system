## Context

`infra-database`、`infra-redis`、`infra-readiness`、`infra-ci` 及全部业务域已交付。当前 `Settings` 含 `DATABASE_URL`、`REDIS_URL`；readiness 聚合 MySQL + Redis；Alembic 单入口 `alembic/` 仅管理 MySQL；`task ci` / `task dev` 对 Redis/PG 的服务依赖纪律不一致（`test:reports` 有 `db:up`+`redis:up`，`ci`/`test`/`dev` 无统一 deps）。

架构与 ADR-002 约定：MySQL 为业务写源；AI 检索上下文走 **PostgreSQL + pgvector**（独立 Base 与 Alembic 入口，见 user-auth design 预留）；本地 devbox、CI service container、同一套 integration 测试；**不**采用本地 docker-compose。

后续 change（`ai-rag-acl-index`、`ai-support-agent`）将消费 PG 与 Embedder，但 **本 change 不实现索引或 RAG 业务**。

约束：

- infra **不得** import 任何业务域模块
- AI 库 ORM 使用 **`AiBase`**（与 MySQL `Base` 分离）；首条 migration 仅 infra 验证表
- 数据库/测试命令须 `devbox run --` 包装
- integration 测试使用 `AsyncClient`；PG integration 须连接 **真实 devbox/CI 实例**

## Goals / Non-Goals

**Goals:**

- 本地 devbox PostgreSQL（含 pgvector）+ `task pg:up` / `pg:down` + `pg_isready` 轮询
- CI `services.postgres`（`pgvector/pgvector:pg16` 或等价 + healthcheck）+ `AI_DATABASE_URL`
- 必填 `AI_DATABASE_URL`；dev/test **双库** `ecommerce_ai_dev` / `ecommerce_ai_test`
- `app/infra/ai_database.py`：async PG engine/session、`get_ai_engine()`、`reset_ai_engine()`
- `app/infra/embedder.py`：`Embedder` 协议、`MockEmbedder`、厂商 API 骨架、`get_embedder()`、**维度 fail-fast**
- `alembic_ai/` 第二入口；revision 001：`vector` extension + `_infra_ai_migration_smoke`
- readiness 聚合 **mysql + redis + postgresql**
- **Task 服务依赖收编**（见 Decision 12）
- integration 测试：AI migration smoke、embedder 维度、向量 CRUD、readiness 扩展
- 更新 README、ADR-002、architecture、`.env.example`、`openspec/config.yaml`

**Non-Goals:**

- 商品索引、events、Outbox、Celery、LangChain
- `product_embedding_chunks` 等业务表
- support / catalog 业务 API 变更
- CI 调用真 Embedding API
- PG HA、生产连接池调优、docker-compose 本地 PG

## Decisions

### 1. 本地提供方式：devbox services（非 docker-compose）

**选择**：devbox 引入 PostgreSQL（pin 大版本，如 16），确保 `CREATE EXTENSION vector` 可用；`scripts/devbox_pg_up.sh` / `_down.sh` 镜像 Redis 脚本（启动 → `pg_isready` 轮询 → 建 `ecommerce_ai_dev` / `ecommerce_ai_test`）。

**理由**：与 MySQL/Redis ADR-002 策略一致。

**备选**：本地 docker-compose PG（ADR 已否决）；裸 apt install（不可复现）。

**风险**：devbox 官方 PG 可能不含 pgvector → apply 前须验证；若不可用，devbox 自定义 plugin 或文档化替代方案（见 Open Questions）。

### 2. CI 提供方式：GitHub Actions service container

**选择**：

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    env:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ecommerce_ai_test
    ports: ["5432:5432"]
    options: >-
      --health-cmd="pg_isready -U postgres"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=5
env:
  AI_DATABASE_URL: postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ecommerce_ai_test
  EMBEDDING_PROVIDER: mock
  EMBEDDING_DIMENSION: "1024"
```

**理由**：与 `services.mysql` / `services.redis` 对称；healthcheck 通过后 job steps 才执行。

**备选**：runner apt install postgresql（难管版本与 pgvector）。

### 3. 双 Base、双 Alembic

**选择**：

| MySQL（business） | PostgreSQL（AI read） |
|-------------------|------------------------|
| `app/infra/database.py` → `Base` | `app/infra/ai_database.py` → `AiBase` |
| `alembic/` | `alembic_ai/` + `alembic_ai.ini` |
| `task migrate` | `task migrate:ai` |
| `DATABASE_URL` | `AI_DATABASE_URL` |

**理由**：user-auth design 已预留；避免 MySQL migration 误用 `vector` 类型；AI 库可独立 reindex/backup。

### 4. 配置：`AI_DATABASE_URL` 与 Embedding 必填项

**选择**：

| 字段 | 说明 |
|------|------|
| `ai_database_url` | 必填，asyncpg URL |
| `embedding_provider` | `mock` \| `zhipu` \| `dashscope`；CI 固定 `mock` |
| `embedding_model` | 厂商模型 id；mock 可忽略 |
| `embedding_dimension` | **须显式配置**（Settings **无** pydantic default）；`.env.example` 与 CI 示例值为 **1024** |
| `embedding_api_key` | mock 可空；真 API 本地 `.env` 配置 |

**理由**：与 `database_url` / `redis_url` 同级纪律；缺失即 Settings 校验失败；migration 001 写死 `vector(1024)`，变更维度须新 revision + 全量 reindex。

### 5. Embedder 抽象与维度校验

**选择**：

- 模块：`app/infra/embedder.py`
- 协议：`embed_texts(texts: list[str]) -> list[list[float]]` + `dimension: int` 属性
- `MockEmbedder`：确定性伪向量（如 hash 填充），维度 = `embedding_dimension`
- 厂商实现：`ZhipuEmbedder` / `DashscopeEmbedder` 骨架（httpx 调 API）；apply 时至少 Mock 全绿，厂商实现可 stub + 单测 mock
- **启动校验**：应用 factory 或 embedder 模块加载时，`get_embedder().dimension == settings.embedding_dimension`，否则 **RuntimeError**
- **写入校验**（向量 smoke 测试覆盖）：向量长度 ≠ dimension → 拒绝

**理由**：索引与检索必须同一 embedding 空间；换模型须 reindex + 新 migration，禁止静默写坏 pgvector。

**备选**：裸 SDK 散落各模块（违反 DRY 与测试隔离）。

### 6. 首条 AI migration：infra smoke 表

**选择**：表 `_infra_ai_migration_smoke`（归属 **infra**，非业务域）：

| 列 | 类型 |
|----|------|
| `id` | UUID PK |
| `note` | VARCHAR |
| `embedding` | `vector(1024)` |
| `created_at` | TIMESTAMPTZ |

ORM：`app/infra/models/ai_migration_smoke.py` 映射 `AiBase`。

**演示**：MockEmbedder → insert → pgvector 相似度查询 top-1 命中。

**不在本 change 建**：`product_embedding_chunks`（Change 2）。

### 7. 客户端：asyncpg + SQLAlchemy 2 async

**选择**：

- 依赖：`asyncpg`、`pgvector`（SQLAlchemy 集成）
- 懒加载 `AsyncEngine` + `async_sessionmaker`（镜像 `database.py`）
- `reset_ai_engine()` 供 integration autouse（镜像 `reset_engine` / `reset_redis`）
- 禁止业务域 / 未来 `ai/` 模块自行 `create_async_engine` 连 AI 库（仅 infra 持有）

### 8. readiness 语义

**选择**：

- `ready` ⇔ `mysql` ok **且** `redis` ok **且** `postgresql` ok
- `checks: { mysql, redis, postgresql }` 各 `ok` \| `unavailable`
- 实现：**镜像** `is_mysql_ready()` / `is_redis_ready()` 纪律：
  - `_ping_postgresql()`：`create_async_engine(settings.ai_database_url)` + `SELECT 1` + 可选 `SELECT 1 FROM pg_extension WHERE extname='vector'`
  - `is_postgresql_ready()`：sync 入口；无 running loop 时 `asyncio.run(_ping_postgresql())`；pytest-asyncio 等已有 loop 时 `ThreadPoolExecutor` + `asyncio.run`（与 MySQL 一致）
  - **不**引入 psycopg/psycopg2 等 sync 驱动（AI 库 URL 为 `postgresql+asyncpg`，readiness 仍用独立短生命周期 async engine）

**理由**：PG 成为与 Redis 同级的硬依赖；复用既有 readiness 模式，避免双驱动栈与事件循环冲突。

### 9. Alembic 第二入口命令

**选择**：

```text
task migrate:ai    → uv run alembic -c alembic_ai.ini upgrade head
task migrate:all   → task migrate && task migrate:ai
```

CI test job：在现有 `alembic upgrade head` 之后增加 `uv run alembic -c alembic_ai.ini upgrade head`（或 `task migrate:all` 若 workflow 改用 task）。

### 10. 测试策略

| 项 | 策略 |
|----|------|
| AI migration smoke | `tests/ops/test_ai_migration_smoke.py`（镜像 `test_migration_smoke.py`） |
| PG 客户端 | `tests/infra/test_pg.py` |
| Embedder | `tests/infra/test_embedder.py`（mock 维度、fail-fast） |
| readiness | **扩展** `tests/ops/test_readiness.py` |
| PG fixture | session `ai_database_url`；integration autouse `reset_ai_engine()` |
| CI | 不调真 Embedding API |

Marker 文案更新：`integration` 说明含 PG + `task pg:up`。

### 11. 文档同步

须在同一 change 更新：

- `README.md`（`task ci` deps、三库、`pg:up`）
- `docs/decision/ADR-002-测试与数据库策略.md`（PG 小节 + Task 表）
- `docs/architecture.md`（infra 模块、§8.3 CI、readiness 三库）
- `openspec/config.yaml`（AI 栈上下文）
- `.env.example`（`AI_DATABASE_URL`、`EMBEDDING_*` 示例值 1024）
- README / ADR-002 写明本地 integration 须在 **`.env.test`**（gitignored）同步上述变量；CI 由 workflow env 覆盖

### 12. Taskfile 服务依赖收编（**修正 infra-redis Decision 9 遗留**）

**选择**：

| Task | deps | 说明 |
|------|------|------|
| `test` | **无** | CI 直接调用；不在 runner 上跑 devbox |
| `ci` | `db:up`, `redis:up`, `pg:up` | 本地一条龙；cmds 在 `test` 前加 `migrate:all` |
| `dev` | `db:up`, `redis:up` | readiness + SMS 需要 Redis |
| `migrate` | `db:up` | |
| `migrate:ai` | `pg:up` | |
| `test:reports` | `db:up`, `redis:up`, `pg:up` | |

**理由**：

- 本地 `task ci` 不再要求开发者手动记 `db:up`/`redis:up`/`pg:up`
- CI 仍用 workflow `services` + healthcheck；**不**给 `task test` 加 devbox deps
- `task dev` 补 `redis:up` 消除 readiness 503 与文档不一致

**与 ADR-002 旧文冲突**：本 change **MODIFIED** infra-ci spec，以新 Task 行为为准。

### 13. Change 2 接口契约（仅 design 记录，本 change 不实现）

后续 `ai-rag-acl-index` **SHALL** 仅使用：

```python
from app.infra.ai_database import get_ai_session_factory  # 或等价
from app.infra.embedder import get_embedder
```

`alembic_ai/002_*` 中 `vector(1024)` 维度 **SHALL** 与本 change 001 一致。

## Risks / Trade-offs

- **[Risk] devbox PG 无 pgvector** → apply 前验证 `CREATE EXTENSION vector`；Open Questions 留备选
- **[Risk] readiness 硬依赖 PG 后，未 `pg:up` 时 `/health/ready` 503** → 可接受；`/health` 不变；`task dev` 暂不 dep `pg:up`（业务 API 尚不连 PG）
- **[Risk] 三 service 增加 CI 内存/时间** → 可接受；不对 HA 拓扑测试
- **[Risk] 维度写死 1024，换 embedding 模型须 migration + reindex** → 文档与 spec 写 SHALL；Change 2 负责 reindex CLI
- **[Risk] `task ci` deps 在已运行 compose 时与 mysql/redis 脚本交互** → 复用现有 redis/mysql 脚本「已就绪则跳过」逻辑

## Migration Plan

1. 合并后：开发者 `devbox run -- task pg:up`；`.env` / `.env.test` 补充 `AI_DATABASE_URL` 与 `EMBEDDING_*`
2. 执行 `devbox run -- task migrate:all` 初始化 AI 库
3. 无 MySQL 业务数据迁移；AI 库为新建
4. 回滚：revert PG 依赖、readiness 第三项、Task deps；drop AI 库（开发环境）

## Open Questions

- devbox PostgreSQL 是否自带 pgvector：**apply Task 2 前须本地验证**；若否，在 devbox 插件或 init SQL 中安装
- 厂商 Embedder 是否在 apply 阶段实现完整 HTTP 调用，或仅 Mock + 接口骨架：**建议 Mock 全测 + 厂商 stub**，真 API 留给本地 `.env` 手动验证
