# e-commerce-system

AI 赋能电商个人练习项目。当前处于 **工程壳 + 数据库基础设施（Task 1）** 阶段：FastAPI 入口、devbox MySQL、Taskfile 数据库命令与 CI 门禁已就绪；Alembic / readiness / integration 测试在后续 Task 中完成。

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

# 5. 运行本地 CI（ruff + pytest；当前不依赖 MySQL）
task ci

# 6. 启动开发服务器（自动依赖 db:up）
task dev
```

开发服务器默认 `http://127.0.0.1:8000`。存活探针：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
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
| `task ci` | 本地 CI：`ruff` + `test`（**不**自动启动 MySQL） |
| `task dev` | 先 `db:up`，再 `uvicorn app.main:app --reload` |

### 数据库（本地 devbox）

| 命令 | 说明 |
|------|------|
| `task db:up` | 启动 MySQL，确保 `ecommerce_dev` / `ecommerce_test` 存在 |
| `task db:down` | 停止 MySQL（socket shutdown + process-compose） |
| `task db:reset` | `db:down` → 删除 `mysql-data/` → `db:up`（慎用） |
| `task migrate` | `alembic upgrade head`（需 `.env` 与 Alembic 脚手架，Task 4+） |
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
- CI 使用 **TCP** `127.0.0.1:3306`（GitHub Actions mysql service container，Task 5.2）

本地与远程 CI 的 **lint + unit 测试** 均执行 `task ci`；含 integration 的完整验证需在本地先 `task db:up`，CI 侧待 workflow 更新。

## 环境变量

仓库只提交 `.env.example`；每人本地复制为 `.env`：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `APP_ENV` | `development` / `test` / `production` |
| `DATABASE_URL` | 本地用 socket URL；跑 integration 测试时改为 `ecommerce_test` |

## 分支工作流

```text
feature/* ──PR──▶ dev ──PR──▶ main（可部署线）
```

| 场景 | 说明 |
|------|------|
| feature 分支开发 | 从 `dev` 切出，本地 `task ci` 通过后提 PR |
| 合入 dev | PR → `dev` 触发 GitHub Actions CI |
| 合入 main | `dev` → `main` PR，CI 通过后可部署 |

feature 分支直接 push **不**触发远程 CI（节省配额）；合入前通过 PR 验证。

## CI

Workflow：`.github/workflows/ci.yml`

| 事件 | 分支 |
|------|------|
| `pull_request` | `dev`, `main` |
| `push` | `dev`, `main` |

GitHub Actions 使用 **commit SHA** 锁定 action 版本（见 `.cursor/rules/github-actions-pinning.mdc`）。

## Definition of Done（DoD）

单个 OpenSpec change 完成标准：

1. 本地 `task ci` 全绿
2. push 后远程 GitHub Actions 全绿
3. 文档已更新（README、architecture 等）
4. 使用 `/opsx:archive` 归档 change

## 文档

- [架构设计](docs/architecture.md)
- [devbox MySQL 竞态条件排查](docs/troubleshooting/devbox-mysql-竞态条件.md)
- [OpenSpec 变更](openspec/changes/)
