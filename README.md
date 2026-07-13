# e-commerce-system

AI 赋能电商个人练习项目。当前处于 **user 业务域（认证）** 阶段：在数据库基础设施之上已交付用户注册/登录、JWT、`GET /users/me` 与 `users` 表迁移；health/readiness 探针与 CI integration 测试（24 项）已就绪。

## 前置条件

- [devbox](https://www.jetify.com/devbox)（推荐在 **WSL2** 下使用）
- Git

本地工具链由 devbox 提供：Python 3.13、uv、go-task、MySQL 8.0。

> **重要**：所有 `task` 命令（含 `db:*`）须在 `devbox shell` 内执行。

## 快速开始

```bash
# 1. 进入 devbox 环境（必须）
devbox shell

# 2. 安装 Python 依赖
task sync

# 3. 配置环境变量（本地私有，不入库）
cp .env.example .env

# 4. 启动本地 MySQL 并创建 dev/test 双库
task db:up

# 5. 执行迁移（dev 库）
task migrate

# 6. 运行本地 CI（ruff + pytest；含 integration，需 db:up）
task ci

# 7. 启动开发服务器（自动依赖 db:up）
task dev
```

开发服务器默认 `http://127.0.0.1:8000`（须已配置 `.env` 中的 `DATABASE_URL`）。

存活探针：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

就绪探针（检查 MySQL 连通性）：

```bash
curl http://127.0.0.1:8000/health/ready
# {"status":"ready","checks":{"mysql":"ok"}}
```

认证 API（须已 `task migrate` 且 `.env` 含 `JWT_SECRET_KEY`）：

```bash
# 注册（201，返回 access_token 与 user）
curl -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"password123"}'

# 登录（200）
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"password123"}'

# 当前用户（Bearer token）
curl http://127.0.0.1:8000/users/me \
  -H "Authorization: Bearer <access_token>"
```

验证 MySQL 双库（可选）：

```bash
mysql -u root --socket=/tmp/e-commerce-system-mysql.sock \
  -e "SHOW DATABASES LIKE 'ecommerce_%';"
```

## Task 命令

### 通用

| 命令 | 说明 |
|------|------|
| `task sync` | `uv sync`，同步 Python 依赖 |
| `task ruff` | 运行 ruff lint |
| `task test` | 运行 pytest |
| `task ci` | 本地 CI：`ruff` + `test`（**不**自动启动 MySQL；integration 需先 `db:up`） |
| `task dev` | 先 `db:up`，再 `uvicorn app.main:app --reload` |

### 数据库（本地 devbox）

| 命令 | 说明 |
|------|------|
| `task db:up` | 启动 MySQL，确保 `ecommerce_dev` / `ecommerce_test` 存在 |
| `task db:down` | 停止 MySQL（socket shutdown + process-compose） |
| `task db:reset` | `db:down` → 删除 `mysql-data/` → `db:up`（慎用） |
| `task migrate` | `alembic upgrade head`（默认 `DATABASE_URL` → dev 库） |
| `task migrate:new -- "描述"` | 新建 Alembic revision（autogenerate） |

实现脚本：`scripts/devbox_mysql_{up,down,reset}.sh`。

### `db:up` 预期输出

MySQL 已在运行：

```text
MySQL 数据目录: .../mysql-data
已有库: ecommerce_dev, ecommerce_test
```

冷启动或 `db:reset` 后：

```text
启动 MySQL...
MySQL 已就绪；数据目录: .../mysql-data；已有库: ecommerce_dev, ecommerce_test
```

## 本地 MySQL 与双库

| 库名 | 用途 |
|------|------|
| `ecommerce_dev` | `task dev`、`task migrate` 默认目标 |
| `ecommerce_test` | pytest `@integration` 测试（零副作用靠 transaction rollback） |

- 数据目录：`mysql-data/`（已 `.gitignore`）
- 本地连接：**unix socket**（非 TCP 3306），见 `.env.example` 与 `devbox.d/mysql80/my.cnf`
- CI 使用 **TCP** `127.0.0.1:3306`（GitHub Actions mysql service container）

本地与远程 CI 均执行 `task ci`（ruff + pytest）。本地须先 `task db:up`；CI 在 workflow 内自动启动 mysql service、建库、`alembic upgrade head` 后再跑测试。详见 [测试与数据库策略](docs/decision/测试与数据库策略.md)。

## 环境变量

仓库只提交 `.env.example`；每人本地复制为 `.env`：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `APP_ENV` | `development` / `test` / `production` |
| `DATABASE_URL` | 本地用 socket URL；跑 integration 测试时改为 `ecommerce_test` |
| `JWT_SECRET_KEY` | JWT 签名密钥（≥ 32 字节）；本地与 CI 均必填 |
| `JWT_ISSUER` | 可选，默认 `e-commerce-system` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 可选，默认 `30` |

## 分支工作流

```text
feature/* ──PR──▶ dev ──PR──▶ main（可部署线）
```

| 场景 | 说明 |
|------|------|
| feature 分支开发 | 从 `dev` 切出，本地 `task db:up` + `task ci` 通过后提 PR |
| feature 远程 CI | push 不自动触发；可用 **Actions → CI → Run workflow**（`workflow_dispatch`）或开 Draft PR → `dev` |
| 合入 dev | PR → `dev` 触发 GitHub Actions CI |
| 合入 main | `dev` → `main` PR，CI 通过后可部署 |

feature 分支直接 push **不**自动跑远程 CI（节省配额）；合入前通过 PR 或手动触发验证。

## CI

Workflow：`.github/workflows/ci.yml`

| 事件 | 分支 / 方式 |
|------|-------------|
| `pull_request` | `dev`, `main` |
| `push` | `dev`, `main` |
| `workflow_dispatch` | 任意分支手动触发（feature 开发验证用） |

CI job 顺序：mysql service 就绪 → 建 `ecommerce_test` → `alembic upgrade head` → `task ci`（workflow `env` 含 `DATABASE_URL` 与 `JWT_SECRET_KEY`）。

```bash
# feature 分支手动触发远程 CI（CLI）
gh workflow run ci.yml --ref feature/infra-database
```

GitHub Actions 使用 **commit SHA** 锁定 action 版本（见 `.cursor/rules/github-actions-pinning.mdc`）。

## Definition of Done（DoD）

单个 OpenSpec change 完成标准：

1. 本地 `task ci` 全绿
2. push 后远程 GitHub Actions 全绿
3. 文档已更新（README、architecture 等）
4. 使用 `/opsx:archive` 归档 change

## 文档

- [架构设计](docs/architecture.md)
- [测试与数据库策略（ADR）](docs/decision/测试与数据库策略.md)
- [集成测试 AsyncClient 与 Event Loop 冲突（排错）](docs/troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md)
- [devbox MySQL 竞态条件排查](docs/troubleshooting/devbox-mysql-竞态条件.md)
- [OpenSpec 变更](openspec/changes/)
