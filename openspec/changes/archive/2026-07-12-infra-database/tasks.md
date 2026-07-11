## 1. 依赖与 devbox MySQL

- [x] 1.1 在 `pyproject.toml` 添加 `sqlalchemy[asyncio]`、`asyncmy`、`alembic`、`pydantic-settings`、`pytest-asyncio`（若需要）；执行 `uv sync`
- [x] 1.2 配置 `devbox.json` MySQL 8.0 service（datadir `mysql-data/`）；更新 `.env.example`（`DATABASE_URL`、`APP_ENV`、dev/test 库说明）
- [x] 1.3 扩展 `Taskfile.yml`：`db:up`、`db:down`、`db:reset`、`migrate`、`migrate:new`；`dev` depends `db:up`；保持 `ci` 与 `dev` 分离
- [x] 1.4 精简 db 脚本输出：`scripts/devbox_mysql_{up,down,reset}.sh`；抑制 `mysqld`/`devbox services` 噪音；`db:down` 增加 socket shutdown；更新 troubleshooting 与 design 文档

## 2. ADR 与 Cursor rules

- [x] 2.1 编写 `docs/decision/测试与数据库策略.md`（devbox vs CI service、双库、rollback、asyncmy、不用 SQLite）
- [x] 2.2 添加 `.cursor/rules/cross-domain-imports.mdc`（禁止跨域 import ORM/repository）

## 3. TDD — 失败测试（红）

- [x] 3.1 在 `pyproject.toml` 注册 `integration` marker；扩展 `tests/conftest.py`（async `db_session` rollback fixture、test `DATABASE_URL`）
- [x] 3.2 按 `specs/infra-readiness/spec.md` 编写 `tests/infra/test_readiness.py`（200 / 503 场景）；**不编写** readiness 实现
- [x] 3.3 按 `specs/infra-database/spec.md` 编写 `tests/infra/test_database.py`（`SELECT 1`）与 `tests/infra/test_migration_smoke.py`（Alembic upgrade + smoke CRUD）；**不编写** database/readiness 实现与 migration
- [x] 3.4 运行 `task db:up` 后 `task test`，确认相关测试失败（红），记录预期失败原因
  - **红阶段失败原因**（`devbox run -- task db:up` + `devbox run -- task test`）：
    - `test_get_db_select_one`：`ModuleNotFoundError: No module named 'app.infra.database'`（§4.1 尚未实现）
    - `test_alembic_upgrade_head_creates_smoke_table`：`No 'script_location' key found in configuration`（`alembic/` 尚未初始化，§4.2）
    - `test_migration_smoke_crud` / `test_migration_smoke_rollback_zero_side_effect`：`ModuleNotFoundError: No module named 'app.infra.models'`（ORM 与 migration 尚未实现，§4.2）
    - `test_readiness_returns_200_when_mysql_ok`：`404 Not Found`（`/health/ready` 路由未挂载，§4.3）
    - `test_readiness_returns_503_when_mysql_unavailable`：`AttributeError: module 'app.infra' has no attribute 'readiness'`（readiness 模块尚未实现，§4.3）
    - `test_readiness_content_type_is_json`：`404` 非 200/503（同上）
  - **仍通过**：`tests/health/test_health.py` 两项（liveness 已实现，不依赖 DB）

## 4. 核心实现（绿）

- [x] 4.1 实现 `app/infra/config.py`、`app/infra/database.py`（async engine、AsyncSession、`get_db`、`Base`）
- [x] 4.2 初始化 `alembic/`；添加 `_infra_migration_smoke` ORM 与首条 migration；`task migrate` 可在 dev/test 库执行
- [x] 4.3 实现 `app/infra/readiness/`（schemas、service、router）并在 `app/main.py` 挂载；使 readiness 与 database/smoke 测试通过

## 5. 本地验证与 CI

- [x] 5.1 运行 `task ci` 确认本地 lint + test 全绿；手动验证 `task dev` 后 `curl /health` 与 `curl /health/ready`
- [x] 5.2 更新 `.github/workflows/ci.yml`：mysql service container、创建 `ecommerce_test`、`alembic upgrade head`、设置 `DATABASE_URL`、`task ci`；增加 `workflow_dispatch` 供 feature 分支手动触发
- [x] 5.3 push 并确认 GitHub Actions 全绿（`workflow_dispatch` 触发 run #29159435667 ✓）

## 6. 文档与 DoD

- [x] 6.1 更新 `README.md`（db 命令、双库、dev vs CI、readiness 演示）与 `docs/architecture.md` 目录结构
- [x] 6.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿（run #29159435667）、文档已更新；可执行 `/opsx:archive` 归档

> **Apply 约定**：严格 TDD，§3 完成前不得开始 §4；每个 apply 会话建议只完成 1–2 个 task。
