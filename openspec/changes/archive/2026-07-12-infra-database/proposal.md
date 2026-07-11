## Why

工程壳（`bootstrap-engineering-shell`）已提供 FastAPI 入口、liveness 探针与 CI 门禁，但尚未接入 MySQL、异步 SQLAlchemy、Alembic 迁移与 readiness 探针。后续 user/catalog/ordering 等业务域均依赖持久化与迁移管线，需要在第一个业务 change 之前完成数据库基础设施，使开发、测试与 CI 共享同一套 schema 真相来源（Alembic migration）。

## What Changes

- 本地通过 **devbox MySQL 服务** 提供 MySQL 8.0（`ecommerce_dev` / `ecommerce_test` 双库，同一实例）
- 引入 **asyncmy** + **SQLAlchemy 2 AsyncSession** 全异步数据访问层（`app/infra/config.py`、`app/infra/database.py`、`get_db` 依赖）
- 初始化 **Alembic** 迁移管线，首条 migration 创建 infra 验证表 `_infra_migration_smoke`（非业务表）
- 新增 **`GET /health/ready`** 聚合 readiness 端点，统一 JSON 格式（`status` + `checks.mysql`），为后续结构化日志与 pg 检查预留扩展
- 扩展 **pytest**：`@pytest.mark.integration`、transaction rollback 零副作用、readiness 烟雾测试、migration smoke CRUD 测试
- **CI**：GitHub Actions **mysql service container**；job 内建库 → `alembic upgrade head` → pytest（与本地 devbox 环境分离，同一套用例）
- 扩展 **Taskfile**：`db:up` / `db:down` / `db:reset` / `migrate` / `migrate:new`；`task dev` 依赖 `db:up`；`task ci` 与 `task dev` 分离；db 命令由 `scripts/devbox_mysql_{up,down,reset}.sh` 实现，输出按场景精简
- 新增 **ADR**（`docs/decision/` 一篇一主题）与 **`.cursor/rules`** 跨域 import 纪律
- 更新 `.env.example`、`README.md`、`docs/architecture.md`

## Non-goals

- 不实现任何业务域（user、catalog、ordering）及业务表（users/products/orders 等）
- 不实现 JWT / auth middleware（留给后续 user change）
- 不使用 SQLite 作为测试替身（测试与 CI 均使用 MySQL）
- 不使用同步 SQLAlchemy 或 PyMySQL/aiomysql（选定 asyncmy + 全 async）
- 本地不使用 docker-compose 提供 MySQL（本地 devbox；CI 用 service container）
- 不实现 CD / 生产部署 / Docker 镜像构建
- 不在 devbox 中打包 Docker（Docker 由 WSL 环境单独提供，本 change 不依赖）

## Capabilities

### New Capabilities

- `infra-database`: 异步 MySQL 连接、配置、Session 依赖、Alembic 脚手架、`_infra_migration_smoke` 迁移验证表
- `infra-readiness`: 聚合 readiness 探针 `GET /health/ready`，检查 MySQL 连通性，统一响应体格式

### Modified Capabilities

（无。`GET /health` liveness 行为不变，`infra-health` 规格不修改。）

## Impact

- **业务域**: `infra`（config、database、readiness；非业务限界上下文）
- **新增/修改文件**: `app/infra/config.py`、`app/infra/database.py`、`app/infra/readiness/`（或扩展 health 模块）、`alembic/`、`tests/infra/`、`tests/conftest.py`、`.github/workflows/ci.yml`、`Taskfile.yml`、`pyproject.toml`、`devbox.json`（MySQL 服务）、`.env.example`、`.cursor/rules/`、`docs/decision/`
- **API**: 新增 `GET /health/ready`；`GET /health` 不变
- **依赖**: sqlalchemy[asyncio]、asyncmy、alembic、pydantic-settings
- **分支**: 基于 `dev` 的 `feature/infra-database`
