## 1. TDD 红：失败测试

- [x] 1.1 新增 `tests/ops/test_ai_migration_smoke.py`：AI 库 migrate 后 `vector` 扩展与 `_infra_ai_migration_smoke` 表（红）
- [x] 1.2 新增 `tests/infra/test_pg.py`：AI 库 `SELECT 1`、向量 insert + 相似度查询 smoke（红）
- [x] 1.3 新增 `tests/infra/test_embedder.py`：`MockEmbedder` 维度、配置不一致 fail-fast（红）
- [x] 1.4 扩展 `tests/ops/test_readiness.py`：三库 checks（含 `postgresql` unavailable/ok 场景）（红）
- [x] 1.5 更新 `pyproject.toml` integration marker 文案（含 PG + `task pg:up`）

## 2. 依赖与 devbox / Taskfile

- [x] 2.1 `pyproject.toml` 增加 `asyncpg`、`pgvector`；`uv sync`
- [x] 2.2 `app/infra/config.py` 增加 `AI_DATABASE_URL`、`EMBEDDING_*`（`embedding_dimension` 必填、无 default）；更新 `.env.example`（示例 `EMBEDDING_DIMENSION=1024`）
- [x] 2.2b README / ADR-002 写明本地 integration 须在 `.env.test` 同步 `AI_DATABASE_URL` 与 `EMBEDDING_*`（`.env.test` gitignored；CI 由 workflow env 覆盖）
- [x] 2.3 devbox 引入 PostgreSQL（含 pgvector 验证）；`scripts/devbox_pg_up.sh` / `devbox_pg_down.sh`
- [x] 2.4 `Taskfile.yml`：`pg:up`/`pg:down`、`migrate:ai`、`migrate:all`；`ci` deps（db+redis+pg）+ migrate:all；`dev` deps + redis；`migrate` deps db；`test:reports` deps + pg
- [x] 2.5 验证 devbox：`devbox run -- task pg:up` 就绪且双 AI 库存在

## 3. AI 数据库与 Alembic 第二入口

- [ ] 3.1 实现 `app/infra/ai_database.py`（`AiBase`、`get_ai_engine`、`get_ai_session_factory`、`reset_ai_engine`）
- [ ] 3.2 新增 `app/infra/models/ai_migration_smoke.py` 与 `alembic_ai/`（`env.py`、revision 001：`vector` + smoke 表 `vector(1024)`）
- [ ] 3.3 `tests/conftest.py`：integration autouse `reset_ai_engine()`；session `ai_database_url` fixture（若需要）
- [ ] 3.4 跑绿 §1 migration smoke 与 PG 测试

## 4. Embedder

- [ ] 4.1 实现 `app/infra/embedder.py`（`Embedder` 协议、`MockEmbedder`、`get_embedder()`、启动维度校验）
- [ ] 4.2 厂商 API 骨架（`ZhipuEmbedder` / `DashscopeEmbedder` stub，单测 mock，CI 不调真 API）
- [ ] 4.3 在 `create_app()` 或等价入口触发 embedder 维度校验
- [ ] 4.4 跑绿 §1 embedder 测试

## 5. Readiness

- [ ] 5.1 `app/infra/readiness/service.py` 增加 `_ping_postgresql()` + `is_postgresql_ready()`（镜像 `is_mysql_ready()`：独立 async engine + ThreadPoolExecutor/`asyncio.run`；不引入 psycopg2）
- [ ] 5.2 更新 `router.py` / `schemas.py`：三库聚合 ready 逻辑
- [ ] 5.3 跑绿 §1 readiness 扩展测试

## 6. CI 与本地 CI

- [ ] 6.1 `.github/workflows/test.yaml`：增加 `services.postgres` + healthcheck；env `AI_DATABASE_URL`、`EMBEDDING_PROVIDER=mock`、`EMBEDDING_DIMENSION`；pytest 前 AI migrate
- [ ] 6.2 `.github/utils/file-filters.yaml`（若需）：纳入 `alembic_ai/**`
- [ ] 6.3 `devbox run -- task ci` 全绿（含 migrate:all + 三库 deps）
- [ ] 6.4 远程 CI：`gh workflow run "Run Tests"` + 确认全绿；更新 `tasks.md` 勾选

## 7. 文档同步

- [ ] 7.1 更新 `README.md`（三库、`task ci`/`dev`/`pg:up` 纪律）
- [ ] 7.2 更新 `docs/decision/ADR-002-测试与数据库策略.md`（PostgreSQL/pgvector 小节 + Task 表）
- [ ] 7.3 更新 `docs/architecture.md`（infra AI 模块、readiness 三库、§8.3 CI）
- [ ] 7.4 更新 `openspec/config.yaml` 项目上下文（AI 读库、Embedding、Task 约定）

## 8. 收尾

- [ ] 8.1 `devbox run -- uv run ruff check .` 与 `task format:check` 通过
- [ ] 8.2 演示验收：`MockEmbedder` → 写入 `_infra_ai_migration_smoke` → 相似度检索命中；`GET /health/ready` 三库 ok
