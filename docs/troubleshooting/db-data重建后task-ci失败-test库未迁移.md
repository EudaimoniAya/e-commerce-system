# db-data 重建后 `task ci` 失败（test 库未迁移）

## 场景

`db:reset`（清空整个 `db-data/`）或全新克隆后，执行 `devbox run -- task ci`，pytest 阶段集中失败，形如：

```text
E   sqlalchemy.exc.ProgrammingError: relation "_infra_ai_migration_smoke" does not exist
E   Failed: seed 管理员登录失败（status=500），请确认 ecommerce_test 已 migrate 且 seed admin 存在
```

涉及 `tests/ai/`（indexing / retrieval / reindex / acl）、`tests/infra/test_pg.py`、`tests/catalog/test_admin_categories.py` 等依赖 schema 的集成测试。

## 问题

数据根全新时，`ecommerce_dev` / `ecommerce_test` / `ecommerce_ai_dev` / `ecommerce_ai_test` 都是空库。`task ci` 内的 `migrate:all` 只迁移 **dev 库**（`alembic` 经 `get_settings().database_url` 读 `.env` → dev）。test 库的 schema **依赖测试里的迁移冒烟测**来初始化。

## 根因

迁移冒烟测会自己执行 `alembic upgrade head`（`APP_ENV_FILE=.env.test`）：

- `tests/catalog/test_admin_seed.py` — MySQL test 库
- `tests/ops/test_ai_migration_smoke.py` — PG AI test 库

但 pytest 按**路径字母序**收集执行：`tests/ai/`、`tests/catalog/` 排在 `tests/ops/` 之前。于是依赖 schema 的集成测试**先跑**、迁移冒烟测**后跑** → 全新 test 库时集成测试必然找不到表。

旧数据根（`mysql-data/`、`postgres-data/`）里 test 库早已迁好，长期掩盖了该顺序依赖；`db-data/` 统一根 + `db:reset`（ADR-002 决策 10）把它常态化暴露。

## 临时处理（未根治）

先迁移 test 库再跑 ci；或首次 ci 失败后**重跑一次**（冒烟测已顺手迁移 test 库，第二次即绿）：

```bash
APP_ENV_FILE=.env.test uv run alembic upgrade head
APP_ENV_FILE=.env.test uv run alembic -c alembic_ai.ini upgrade head
devbox run -- task ci
```

## TODO（结构性修复，已定方案、暂未实施）

- **方案 A（已拍板）**：在 `tests/conftest.py` 增加 **session 级 autouse fixture**，每个 pytest 会话开始前对 test 库跑一遍两条 `alembic upgrade head`（幂等）。使集成测试不再依赖迁移冒烟测的执行顺序，fresh `db-data/` 后 `task ci` 直接全绿。
- 关联：`infra-devbox-services` change（[ADR-002 决策 10](../decision/ADR-002-测试与数据库策略.md)）。
