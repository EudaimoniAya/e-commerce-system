## Context

`bootstrap-engineering-shell` 已交付 FastAPI 入口、`GET /health` liveness、pytest + CI 门禁。当前 `app/infra/` 仅有 `health/` 子模块，无数据库配置、Session 或 Alembic。架构文档规划 `infra/config.py`、`infra/database.py`，业务 MVP 以 MySQL 为唯一写源。

约束来自 explore 决策：

- 本地 MySQL：**devbox services**（非 docker-compose）
- CI MySQL：**GitHub Actions mysql service container**（与本地提供形式不同，同一套 pytest 用例）
- 全 **async**：FastAPI + SQLAlchemy 2 `AsyncSession` + **asyncmy**
- Schema SSOT：**Alembic migration**（不用 `Base.metadata.create_all()` 作为生产路径）
- 双库：同实例 `ecommerce_dev`（开发）+ `ecommerce_test`（测试）
- 12-factor：连接信息经 `DATABASE_URL` 等环境变量注入

## Goals / Non-Goals

**Goals:**

- 提供可复用的 async 数据库基础设施（config、engine、session、`get_db`）
- 初始化 Alembic，首条 migration 创建 `_infra_migration_smoke` 验证表
- 提供 `GET /health/ready` 聚合 readiness（检查 MySQL），统一 JSON 响应格式
- 建立 integration 测试惯例（marker、transaction rollback、CI migrate + pytest）
- 扩展 Taskfile：`task dev` 自动启动 devbox MySQL；`task ci` 与 dev 分离
- 文档：ADR（测试与数据库策略）、`.cursor/rules` 跨域 import 纪律

**Non-Goals:**

- 业务表、JWT、docker-compose 本地 MySQL、SQLite 测试替身、CD 部署

## Decisions

### 1. 异步栈：asyncmy + SQLAlchemy 2 AsyncSession

**选择**：`mysql+asyncmy://` + `create_async_engine` + `async_sessionmaker`；路由与 repository 层使用 `async def`。

**理由**：与 FastAPI 异步模型一致；asyncmy 对 MySQL 8 与 SQLAlchemy 2 async 兼容积极。

**备选**：aiomysql（更老、资料多）、同步 PyMySQL + `def` 路由（与选型不符）。

**Alembic**：迁移脚本使用 **同步 engine**（`mysql+asyncmy` 对应的 sync URL 或独立 sync 连接）执行 `upgrade`/`downgrade`；运行时应用层保持 async。迁移频率低，可接受。

### 2. 本地 MySQL：devbox services

**选择**：在 `devbox.json` 中配置 MySQL 8.0 service（`mysql80@latest`）；数据持久化到项目内 `mysql-data/`（已在 `.gitignore`）；运行态文件（socket、日志）在 `.devbox/virtenv/mysql80/run/`。

**理由**：与 bootstrap 工具链一致（devbox 管 OS 级服务）；WSL2 环境已有 Docker 但本 change 不在本地用 compose 跑 MySQL。

**本地连接（与 CI 不同）**：

| 项 | 本地 devbox | CI service container |
|----|-------------|---------------------|
| 传输 | **unix socket**（`skip-networking`） | **TCP** `127.0.0.1:3306` |
| Socket 路径 | `/tmp/e-commerce-system-mysql.sock` | — |
| `DATABASE_URL` 示例 | `mysql+asyncmy://root@localhost/ecommerce_dev?charset=utf8mb4&unix_socket=/tmp/e-commerce-system-mysql.sock` | `mysql+asyncmy://root@127.0.0.1:3306/ecommerce_test?charset=utf8mb4` |

**`devbox.d/mysql80/my.cnf` 要点**：

- `datadir = ./mysql-data`
- `skip-networking` — 避免 WSL 上 3306 端口冲突与 process-compose 快速重启时的 bind 竞态
- `skip-log-bin` — 本地开发不需要 binlog，减少 `mysql-data/` 体积

**启动**：`task db:up` → `scripts/devbox_mysql_up.sh`（须在 **devbox shell** 内执行；脚本依赖 devbox 提供的 `mysqld`/`mysqladmin` 与 `MYSQL_BASEDIR`）。

**就绪轮询**：`services up -b` 返回后须 `mysqladmin ping` 轮询（最多 60s），详见 `.cursor/rules/service-startup-readiness-polling.mdc` 与 `docs/troubleshooting/devbox-mysql-竞态条件.md`。

### 3. CI MySQL：GitHub Actions service container

**选择**：workflow 增加 `services.mysql`（MySQL 8.0），映射 `3306:3306`；job 内 `CREATE DATABASE ecommerce_test` → `alembic upgrade head` → pytest。

**理由**：Runner 每次 job 全新；MySQL 在 **单次 job 生命周期内** 常驻，供全部 pytest 使用。与本地 devbox 形式不同，但版本、charset、用例一致。

**环境变量**：CI 中 `DATABASE_URL` 指向 `127.0.0.1:3306/ecommerce_test`。

### 4. 双库策略

| 库名 | 用途 | 本地 | CI |
|------|------|------|-----|
| `ecommerce_dev` | `task dev`、`task migrate` 默认目标 | devbox | 不使用 |
| `ecommerce_test` | pytest integration | devbox | 唯一业务库 |

**原则**：CI **不** 使用 `ecommerce_dev`；测试零副作用靠 **transaction rollback**，非每 test 删库。

### 5. 模块布局

```text
app/infra/
├── config.py           # pydantic-settings：database_url, app_env
├── database.py         # async engine, AsyncSession, Base, get_db
├── health/             # 已有 liveness，不依赖 DB
└── readiness/
    ├── router.py       # GET /health/ready
    ├── service.py      # 检查 MySQL（SELECT 1 或 engine connect）
    └── schemas.py      # ReadinessResponse, CheckStatus

app/infra/models/       # 或 app/infra/migration_smoke/
    migration_smoke.py  # _InfraMigrationSmoke ORM（仅 infra 验证）

alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 001_create_infra_migration_smoke.py

tests/
├── conftest.py         # client, async db_session (rollback), integration marker 注册
└── infra/
    ├── test_readiness.py
    ├── test_database.py
    └── test_migration_smoke.py

scripts/                # Task 1 本地 devbox MySQL 运维（须在 devbox shell 内执行）
├── devbox_mysql_up.sh
├── devbox_mysql_down.sh
└── devbox_mysql_reset.sh
```

**readiness 与 health 分模块**：liveness（`/health`）与 readiness（`/health/ready`）职责分离，对应 OpenSpec capability 分离。

### 6. Readiness 响应格式

统一结构，便于后续结构化日志与扩展 `checks.pg`：

```json
{
  "status": "ready" | "not_ready",
  "checks": {
    "mysql": "ok" | "unavailable" | "skipped"
  }
}
```

| 条件 | HTTP | status | checks.mysql |
|------|------|--------|--------------|
| MySQL 可达 | 200 | ready | ok |
| MySQL 不可达 | 503 | not_ready | unavailable |

本 change 仅实现 `mysql` 检查；`pg` 在 AI 阶段 ADDED。

### 7. Alembic 与 `_infra_migration_smoke`

**选择**：首条 revision 创建表 `_infra_migration_smoke`（列：`id` PK、`note` VARCHAR、`created_at`），归属 **infra**（非业务域）。

**理由**：验证 migration 管线 + 提供 integration CRUD 测试目标；dev 与 test 库均在 `alembic upgrade head` 后拥有该表（无害 infra 表）。

**不用** `create_all()` 作为 schema SSOT。

### 8. 测试策略

**Integration marker**：`pytest.mark.integration` 标记需 MySQL 的测试；`pyproject.toml` 注册 marker。

**Session fixture**（每个 test）：

```text
connect → BEGIN → yield AsyncSession → ROLLBACK → close
```

**用例分层**：

| 测试 | 类型 | 说明 |
|------|------|------|
| `test_health_*` | 无 marker | 已有，不依赖 DB |
| `test_readiness_*` | integration | 200 / 503（可 mock engine 测 503） |
| `test_migration_smoke_crud` | integration | 对 `_infra_migration_smoke` 增删改查 |
| `test_alembic_upgrade_head` | integration | CI 与本地 migrate 后表存在 |

**本地**：devbox MySQL 已运行时可重复 pytest；**CI**：每 job 新建 MySQL → 建库 → migrate → 同一套用例。

### 9. Taskfile 命令

| 任务 | 说明 | 入口脚本 |
|------|------|----------|
| `db:up` | 启动 devbox MySQL service，确保 dev/test 双库 | `scripts/devbox_mysql_up.sh` |
| `db:down` | 停止 devbox MySQL service | `scripts/devbox_mysql_down.sh` |
| `db:reset` | 停止并清除 `mysql-data/` 后重新 `db:up`（开发用，慎用） | `scripts/devbox_mysql_reset.sh` |
| `migrate` | `alembic upgrade head`（默认 `DATABASE_URL` → dev 库） | — |
| `migrate:new` | `alembic revision --autogenerate -m "..."` | — |
| `dev` | **depends: db:up** → uvicorn | — |
| `test` | pytest（含 integration；需 test 库可用） | — |
| `ci` | ruff + test（本地模拟；与 `dev` 分离，不自动 db:up） | — |

**说明**：`task ci` 不隐式启动 MySQL，开发者/CI workflow 负责环境就绪；`task dev` 必须自动 `db:up`。`db:up`/`db:down`/`db:reset` 在 devbox shell 内直接调用 bash 脚本，不再嵌套 `devbox run --`。

**脚本输出约定**（`devbox_mysql_up.sh`）：

| 场景 | 输出 |
|------|------|
| MySQL 已就绪 | 两行：`MySQL 数据目录: ...`、`已有库: ecommerce_dev, ecommerce_test` |
| 需启动 / reset | 进度行（初始化、启动）+ 一行摘要：`MySQL 已就绪；数据目录: ...；已有库: ...` |
| 初始化日志 | `mysqld --initialize-insecure` 写入 `.devbox/virtenv/mysql80/run/mysql-init.log`，不刷屏 |
| devbox 噪音 | `devbox services up` stdout 重定向；`mysqladmin ping` 完全静默 |

**停止约定**（`devbox_mysql_down.sh`）：先 `mysqladmin shutdown`（socket），再 `devbox services stop`，避免 process-compose 停止后 mysqld 残留导致 `db:up` 误判已就绪。

### 10. CI workflow 变更

在现有 `task ci` 前增加：

1. mysql service container（health check wait）
2. 创建 `ecommerce_test` 用户/库（或使用 service 默认 root）
3. 设置 `DATABASE_URL` 指向 test 库
4. `alembic upgrade head`
5. `task ci`

### 11. ADR 与 Cursor rules

- `docs/decision/测试与数据库策略.md`：devbox vs CI service、双库、rollback、不用 SQLite、asyncmy 选型摘要
- `.cursor/rules/cross-domain-imports.mdc`：禁止跨域 import ORM/repository；跨域走 service + schema

### 12. 依赖新增

```text
sqlalchemy[asyncio]
asyncmy
alembic
pydantic-settings
```

（pytest-asyncio 若需要 async test fixture）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 本地 devbox MySQL 与 CI service 行为差异 | ADR 文档化；MySQL 8.0 + utf8mb4 对齐；同一 pytest 在 CI 必跑 |
| AsyncSession lazy load 踩坑 | ADR/注释说明；repository 层显式预加载（selectinload/joinedload） |
| Alembic autogenerate 误扫业务表 | 本 change 仅 infra smoke 模型；业务 model 按域分目录后续加入 |
| `task test` 本地无 MySQL 失败 | README 明确先 `task db:up`；失败信息提示 |
| dev 库残留 `_infra_migration_smoke` | 接受；infra 表，不影响业务 |

## Migration Plan

1. 进入 devbox shell：`devbox shell`
2. 复制环境变量：`cp .env.example .env`（本地 `DATABASE_URL` 使用 unix socket，见 `.env.example`）
3. 启动 MySQL：`task db:up`（创建 `ecommerce_dev` / `ecommerce_test`）
4. 迁移（Task 4.2 完成后）：`task migrate`（dev 库）
5. 开发：`task dev`
6. 验证：`curl /health`；实现 readiness 后 `curl /health/ready`
7. 回滚：无业务数据；`alembic downgrade base` 可移除 smoke 表；本地环境彻底重来可用 `task db:reset`

## Open Questions

（无。explore 阶段决策已闭合。）
