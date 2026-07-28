# e-commerce-system

AI 赋能电商个人练习项目。当前已交付 **user 域手机号 + SMS OTP 认证**、**catalog**（店铺 / 类目 / 商品）、**ordering**（买家/卖家订单、购物车 checkout、batch-pay、支付桩与履约），以及 **infra** 横切能力（结构化日志、统一 error JSON、MySQL + **Redis 8**、readiness 双依赖探针）。Alembic 至 migration `008`（users.phone）；本地与 CI integration 测试 **252 项**。

## 前置条件

- [devbox](https://www.jetify.com/devbox)（推荐在 **WSL2** 下使用）
- Git

本地工具链由 devbox 提供：Python 3.13、uv、go-task、MySQL 8.0、**Redis 8.0**。

> **`task check-test-imports` 依赖 `rg`（ripgrep）**：脚本 `scripts/check_no_test_cross_imports.sh` 使用 ripgrep 扫描 test 互 import。Implement `infra-ci-docker` §7 后，`devbox.json` 将包含 `ripgrep`；此前本地可 `sudo apt install ripgrep`。CI lint job 亦须在跑该 Task 前显式安装 ripgrep（不得假设 runner 预装）。

> **重要**：所有 `task` 命令（含 `db:*`、`redis:*`）须在 `devbox shell` 内执行（或使用 `devbox run -- task …`）。

## 快速开始

```bash
# 1. 进入 devbox 环境（必须）
devbox shell

# 2. 安装 Python 依赖
task sync

# 3. 配置环境变量（本地私有，不入库；须含 DATABASE_URL、REDIS_URL、JWT_SECRET_KEY）
cp .env.example .env

# 4. 启动本地 MySQL 并创建 dev/test 双库
task db:up

# 5. 启动本地 Redis 8（readiness 与 integration 测试依赖）
task redis:up

# 6. 执行迁移（dev 库）
task migrate

# 7. 运行本地 CI（ruff + pytest；含 integration，需 db:up + redis:up）
task ci

# 8. 启动开发服务器（自动依赖 db:up；不自动 redis:up）
task dev
```

开发服务器默认 `http://127.0.0.1:8000`（须已配置 `.env` 中的 `DATABASE_URL`、`REDIS_URL`）。

存活探针：

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

就绪探针（检查 **MySQL + Redis** 连通性）：

```bash
curl http://127.0.0.1:8000/health/ready
# {"status":"ready","checks":{"mysql":"ok","redis":"ok"}}
```

> 若未 `task redis:up`，`/health/ready` 返回 503（`redis: unavailable`）；`/health` 仍 200。

认证 API（须已 `task migrate`、`task redis:up`，且 `.env` 含 `JWT_SECRET_KEY` 与 `REDIS_URL`；本地烟雾可设 `SMS_OTP_FIXED_CODE=123456`）：

```bash
# 发送 OTP（200）
curl -X POST http://127.0.0.1:8000/auth/sms/send \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000"}'

# SMS 注册（201，返回 access_token 与 user）
curl -X POST http://127.0.0.1:8000/auth/sms/register \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","code":"123456","password":"password123"}'

# SMS OTP 登录（200）
curl -X POST http://127.0.0.1:8000/auth/sms/login \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","code":"123456"}'

# 手机号 + 密码登录（200）
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"13800138000","password":"password123"}'

# 当前用户（Bearer token）
curl http://127.0.0.1:8000/users/me \
  -H "Authorization: Bearer <access_token>"

# 更新资料（email / nickname）
curl -X PATCH http://127.0.0.1:8000/users/me \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <access_token>" \
  -d '{"email":"demo@example.com","nickname":"演示用户"}'
```

> 旧端点 `POST /auth/register`（email+password）与 `POST /auth/sms/verify` 已移除，返回 404。

店铺 API（须已认证；`POST /shops` 需 Bearer token）：

```bash
# 开店（201）
curl -X POST http://127.0.0.1:8000/shops \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <access_token>" \
  -d '{"name":"我的店铺","description":"简介","logo_url":"https://example.com/logo.png"}'

# 当前用户的店铺（200；无店 404）
curl http://127.0.0.1:8000/shops/me \
  -H "Authorization: Bearer <access_token>"

# 更新店铺（200；可设 status 为 closed 关店）
curl -X PATCH http://127.0.0.1:8000/shops/me \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <access_token>" \
  -d '{"name":"新店名","status":"closed"}'

# 公开店铺详情（无需认证；closed 仍 200）
curl http://127.0.0.1:8000/shops/<shop_id>
```

类目 API（`POST /categories` 须 seed 管理员 Bearer token；`GET /categories` 公开）：

```bash
# 管理员登录（migration 008 seed；本地 dev 库）
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"13800000000","password":"1919810810"}'

# 创建类目（201；非 admin 403）
curl -X POST http://127.0.0.1:8000/categories \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <admin_access_token>" \
  -d '{"name":"数码"}'

# 扁平类目列表（200；空库返回 []）
curl http://127.0.0.1:8000/categories
```

商品 API（`POST/PATCH /products`、`GET /shops/me/products` 须店主 Bearer token 且店铺 active；公开列表/详情无需认证）：

```bash
# 店主创建并上架商品（201；须 category_ids + primary_category_id）
curl -X POST http://127.0.0.1:8000/products \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <shop_owner_token>" \
  -d '{"name":"示例商品","price":"99.00","stock":10,"is_published":true,"category_ids":["<category_id>"],"primary_category_id":"<category_id>"}'

# 店主分页查询本店商品（200；含未上架）
curl "http://127.0.0.1:8000/shops/me/products?limit=20&offset=0" \
  -H "Authorization: Bearer <shop_owner_token>"

# 更新商品（200；非本店 403；closed 店铺 422）
curl -X PATCH http://127.0.0.1:8000/products/<product_id> \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <shop_owner_token>" \
  -d '{"stock":0,"is_published":false}'

# 公开商品列表（仅已上架且店铺 active；可选 ?category_id=）
curl "http://127.0.0.1:8000/products?limit=20&offset=0"

# 公开商品详情（未上架或 closed 店铺 404）
curl http://127.0.0.1:8000/products/<product_id>
```

订单 API（须买家/店主 Bearer token；创建前需可购商品：已上架且店铺 active；禁自购）：

```bash
# 买家下单（201；同店多行；跨店/超卖/未上架 422；自购 403；initiated_by=buyer）
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <buyer_token>" \
  -d '{"items":[{"product_id":"<product_id>","qty":2}]}'

# 卖家为指定买家建单（201；商品须属本店；买家不存在 404、禁用 422；initiated_by=seller）
curl -X POST http://127.0.0.1:8000/shops/me/orders \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <shop_owner_token>" \
  -d '{"buyer_user_id":"<buyer_user_id>","items":[{"product_id":"<product_id>","qty":2}]}'

# 买家分页列表（200；读列表时触发懒释放）
curl "http://127.0.0.1:8000/orders?limit=20&offset=0" \
  -H "Authorization: Bearer <buyer_token>"

# 订单详情（买家或本店店主；读时触发懒释放）
curl http://127.0.0.1:8000/orders/<order_id> \
  -H "Authorization: Bearer <buyer_or_shop_owner_token>"

# 支付桩（200 → confirmed；重复/过期 409；卖家发起的单由指定买家 pay）
curl -X POST http://127.0.0.1:8000/orders/<order_id>/pay \
  -H "Authorization: Bearer <buyer_token>"

# 店主发货（201 → shipped；非 confirmed 409）
curl -X POST http://127.0.0.1:8000/orders/<order_id>/shipments \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <shop_owner_token>" \
  -d '{"note":"已发出"}'

# 买家确认收货（200 → completed）
curl -X POST http://127.0.0.1:8000/orders/<order_id>/confirm-receipt \
  -H "Authorization: Bearer <buyer_token>"

# 买家或店主取消（200 → cancelled；completed 409）
curl -X POST http://127.0.0.1:8000/orders/<order_id>/cancel \
  -H "Authorization: Bearer <buyer_or_shop_owner_token>"

# 店主分页查看本店订单（200；读列表时触发懒释放）
curl "http://127.0.0.1:8000/shops/me/orders?limit=20&offset=0" \
  -H "Authorization: Bearer <shop_owner_token>"

# 批量支付（200；可跨 batch、可子集；须 awaiting_payment）
curl -X POST http://127.0.0.1:8000/orders/batch-pay \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <buyer_token>" \
  -d '{"order_ids":["<order_id>"]}'
```

购物车 API（须买家 Bearer token；列表展示 catalog 实时价，checkout 时快照锁价）：

```bash
# 加购（201 或累加数量）
curl -X POST http://127.0.0.1:8000/cart/items \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <buyer_token>" \
  -d '{"product_id":"<product_id>","qty":1}'

# 购物车列表（按店分组；不可购项在 invalid_items）
curl http://127.0.0.1:8000/cart \
  -H "Authorization: Bearer <buyer_token>"

# 部分 checkout（201；创建 checkout_batch + 按店子单）
curl -X POST http://127.0.0.1:8000/cart/checkout \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer <buyer_token>" \
  -d '{"cart_item_ids":["<cart_item_id>"]}'
```

> 上文 curl 示例仅供**手动调试**；业务主流程与回归由 `task ci`（或 `task test:user` / `test:catalog` / `test:ordering`）中的 pytest integration 覆盖。**不要**新增 `scripts/*_curl_smoke.sh` 类脚本（与 integration 测试重复且不进 CI）。

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
| `task test` | 运行全部 pytest（自动 `APP_ENV_FILE=.env.test`） |
| `task test:user` | 仅 user 域测试（`tests/user/` + `tests/unit/user/`） |
| `task test:catalog` | 仅 catalog 域测试（`tests/catalog/` + `tests/unit/catalog/`） |
| `task test:ordering` | 仅 ordering 域测试（`tests/ordering/`） |
| `task test:infra` | 仅 infra + ops 测试（`tests/infra/` + `tests/ops/`） |
| `task test:unit` | 仅纯单元测试（`tests/unit/`） |
| `task ci` | 本地 CI：`ruff` + test-import 检查（**依赖 `rg`/ripgrep**）+ `test`（**不**自动 `db:up` / `redis:up`） |
| `task check-test-imports` | 用 `rg` 检查 tests 下禁止的 test 模块互 import（见 `scripts/check_no_test_cross_imports.sh`） |
| `task dev` | 先 `db:up`，再 `uvicorn app.main:app --reload` |
| `task test:reports` | 运行 pytest 并生成 Allure HTML 报告（自动 `db:up` + `redis:up`） |
| `task latest:report` | 在浏览器中打开最近生成的 Allure 报告 |

### 数据库（本地 devbox）

| 命令 | 说明 |
|------|------|
| `task db:up` | 启动 MySQL，确保 `ecommerce_dev` / `ecommerce_test` 存在 |
| `task db:down` | 停止 MySQL（socket shutdown + process-compose） |
| `task db:reset` | `db:down` → 删除 `mysql-data/` → `db:up`（慎用） |
| `task migrate` | `alembic upgrade head`（默认 `DATABASE_URL` → dev 库） |
| `task migrate:new -- "描述"` | 新建 Alembic revision（autogenerate） |

实现脚本：`scripts/devbox_mysql_{up,down,reset}.sh`。

### Redis（本地 devbox）

| 命令 | 说明 |
|------|------|
| `task redis:up` | 启动 Redis 8，轮询 `redis-cli ping` 直至 PONG |
| `task redis:down` | 停止 devbox Redis 服务 |

实现脚本：`scripts/devbox_redis_{up,down}.sh`。

### Allure 测试报告（本地）

Allure CLI 需本地安装（非 devbox 提供）。macOS：`brew install allure`；Linux：

```bash
# Ubuntu/Debian
sudo apt-add-repository ppa:qameta/allure
sudo apt update
sudo apt install allure

# 或手动下载：https://github.com/allure-framework/allure2/releases
```

生成并查看报告：

```bash
# 运行测试并生成 Allure 报告（自动 db:up + redis:up）
task test:reports

# 在浏览器中打开报告
task latest:report
```

`reports/` 目录已加入 `.gitignore`，不会提交到仓库。CI 每 matrix job 上传 `allure-results` artifact（14 天保留），供本地下载后 `allure generate` 查看。

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

### `redis:up` 预期输出

```text
Redis 已就绪；端口: 6379；逻辑库: 0（dev）/ 1（test）
```

## 本地 MySQL 与双库

| 库名 | 用途 |
|------|------|
| `ecommerce_dev` | `task dev`、`task migrate` 默认目标 |
| `ecommerce_test` | pytest `@integration` 测试（零副作用靠 transaction rollback） |

- 数据目录：`mysql-data/`（已 `.gitignore`）
- 本地连接：**unix socket**（非 TCP 3306），见 `.env.example` 与 `devbox.d/mysql80/my.cnf`
- CI 使用 **TCP** `127.0.0.1:3306`（GitHub Actions mysql service container）

本地与远程 CI 均执行 `task ci`（ruff + pytest）。本地须先 `task db:up` 与 `task redis:up`；CI 在 workflow 内自动启动 mysql + redis service、建库、`alembic upgrade head` 后再跑测试。详见 [测试与数据库/Redis 策略](docs/decision/测试与数据库策略.md)。

## 本地 Redis 与逻辑库

| 逻辑库 | 用途 |
|--------|------|
| `db 0` | 本地开发（`.env` 中 `REDIS_URL=…/0`） |
| `db 1` | pytest `@integration` 与 CI（`.env.test` / workflow `REDIS_URL`） |

- 本地连接：`redis://127.0.0.1:6379`（TCP）
- CI 使用 **redis:8.0** service container（`127.0.0.1:6379`）
- 业务代码通过 `app/infra/redis.py` 的 `get_redis()` 访问；**禁止**业务域自行 `Redis.from_url`

## 环境变量

仓库只提交 `.env.example`；每人本地复制为 `.env`：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `APP_ENV` | `development` / `test` / `production` |
| `DATABASE_URL` | 本地用 socket URL；integration 测试用 `ecommerce_test` |
| `REDIS_URL` | **必填**；本地 dev 用 `/0`，测试/CI 用 `/1` |
| `JWT_SECRET_KEY` | JWT 签名密钥（≥ 32 字节）；本地与 CI 均必填 |
| `JWT_ISSUER` | 可选，默认 `e-commerce-system` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 可选，默认 `30` |
| `ORDER_RESERVATION_TTL_SECONDS` | 可选，默认 `86400`；待支付订单预留时长，超时懒释放为 `cancelled`/`expired`（pay、详情、**订单列表**路径触发） |

`task test` / CI 通过 `APP_ENV_FILE=.env.test` 加载测试配置（含 `REDIS_URL=…/1`）。

## 分支工作流

```text
feature/* ──PR──▶ dev ──PR──▶ main（可部署线）
```

| 场景 | 说明 |
|------|------|
| feature 分支开发 | 从 `dev` 切出，本地 `task db:up` + `task redis:up` + `task ci` 通过后提 PR |
| feature 远程 CI | push 不自动触发；可用 **Actions → CI → Run workflow**（`workflow_dispatch`）或开 Draft PR → `dev` |
| 合入 dev | PR → `dev` 触发 GitHub Actions CI |
| 合入 main | `dev` → `main` PR，CI 通过后可部署 |

feature 分支直接 push **不**自动跑远程 CI（节省配额）；合入前通过 PR 或手动触发验证。

## CI

Workflow：`.github/workflows/ci.yml`

### 结构

```text
lint:  ruff + check-test-imports（无 services，显式 apt install ripgrep）
test:  5 路 domain matrix 并行：
       user | catalog | ordering | infra | unit
       每 job 独立 mysql + redis services → migrate → pytest --alluredir → upload artifact
```

| 域名 | pytest 路径 |
|------|------------|
| `user` | `tests/user tests/unit/user` |
| `catalog` | `tests/catalog tests/unit/catalog` |
| `ordering` | `tests/ordering` |
| `infra` | `tests/infra tests/ops` |
| `unit` | `tests/unit` |

### 触发

| 事件 | 分支 / 方式 |
|------|-------------|
| `pull_request` | `dev`, `main` |
| `push` | `dev`, `main` |
| `workflow_dispatch` | 任意分支手动触发，可选 `domain`（all/user/catalog/ordering/infra/unit） |

```bash
# CLI 手动触发远程 CI
gh workflow run CI --ref <branch> -f domain=user
```

### Allure 报告

- CI 每 matrix job 上传 `allure-results-<domain>` artifact（保留 14 天）
- 本地 `task test:reports` 生成 HTML；`task latest:report` 浏览器查看
- `reports/` 目录已 `.gitignore`

GitHub Actions 使用 **commit SHA** 锁定 action 版本（见 `.cursor/rules/github-actions-pinning.mdc`）。lint job 中 `check-test-imports` 依赖 `rg`（ripgrep），CI 在 job 内 `apt-get install ripgrep`。

## Docker 镜像

```bash
# 本地构建（验证 Dockerfile 语法）
docker build -t e-commerce-system .

# 远程构建（gh CLI，合入 main 后自动触发或 workflow_dispatch 手动）
gh workflow run "Docker Build" --ref main
```

| 触发 | Tag |
|------|-----|
| `push main` | `latest`、`sha-<short>` |
| `push v*` tag | semver（`v1.0.0`、`v1.0`、`v1`）、`sha-<short>` |

Registry：**GHCR** `ghcr.io/eudaimoniaya/e-commerce-system`

镜像仅含 FastAPI app + 生产依赖（不含 MySQL/Redis/tests）。运行时需环境变量注入 `DATABASE_URL`、`REDIS_URL`、`JWT_SECRET_KEY`。

> **踩坑记录**：`gh workflow run` / GitHub API 只识别**默认分支**上的 workflow 文件。feature 分支新增 `docker-build.yml` 后 `gh workflow run "Docker Build" --ref feature/...` 返回 404。workflow 必须先存在于默认分支才会被 `workflow_dispatch` 事件识别，这是 GitHub Actions 的设计约束。

## 版本策略

| Tag | 含义 |
|-----|------|
| `v1.0.0` | 电商底座 MVP 首次 release（本 change 合入 main 后） |
| `v1.x.0` | 底座完善（engagement、infra-cd-compose 等） |
| `v2.0.0` | AI 平台阶段 |

## Definition of Done（DoD）

单个 OpenSpec change 完成标准：

1. 本地 `task db:up` + `task redis:up` 后 `task ci` 全绿
2. push 后远程 GitHub Actions 全绿
3. 文档已更新（README、architecture、ADR 等）
4. 使用 `/opsx:archive` 归档 change

## 文档

- [架构设计](docs/architecture.md)
- [测试与数据库/Redis 策略（ADR）](docs/decision/测试与数据库策略.md)
- [中间件栈与异常处理（ADR）](docs/decision/中间件栈与异常处理架构决策.md)
- [集成测试 AsyncClient 与 Event Loop 冲突（排错）](docs/troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md)
- [devbox MySQL 竞态条件排查](docs/troubleshooting/devbox-mysql-竞态条件.md)
- [OpenSpec 变更归档](openspec/changes/archive/)
