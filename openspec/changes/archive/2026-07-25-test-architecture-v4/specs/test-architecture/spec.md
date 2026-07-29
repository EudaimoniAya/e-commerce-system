# test-architecture

## Purpose

测试代码四层架构与数据流纪律：Case（Assert-First）、Fixture（fail-fast 瘦身 Context + fixture 依赖链）、Support（helper + builders/results + db 断言/seed）、Utilities（纯函数）。HTTP 集成测通过 SAVEPOINT 单事务隔离；持久状态经 `tests/support/db` 查询与 Arrange，无需 PipelineResult 传递 ID。

## Requirements

### Requirement: Four-layer test architecture

测试代码 SHALL 分为 Case、Fixture、Support、Utilities 四层。Case 层位于 `tests/**/test_*.py`；Fixture 层位于 `tests/conftest.py`；Support 层位于 `tests/support/`（含 `tests/support/db/`、`tests/support/helper/`）；Utilities 为 Support 内无 HTTP/DB 的纯函数。

#### Scenario: Case layer contains only test functions

- **WHEN** 审查 `tests/user/`、`tests/catalog/` 或 `tests/ordering/` 下 `test_*.py`
- **THEN** SHALL 仅含 `test_*` 函数与允许的模块级常量
- **AND** SHALL NOT 含可复用的 HTTP helper 或 DB seed 函数

#### Scenario: Support layer owns HTTP and DB helpers

- **WHEN** 测试需要可复用 HTTP 调用或 DB 状态查询/seed
- **THEN** HTTP helper SHALL 位于 `tests/support/helper/` 域子模块（如 `auth.py`、`catalog.py`、`ordering.py`）
- **AND** DB 断言与 seed helper SHALL 位于 `tests/support/db/`
- **AND** SHALL NOT 位于 `test_*.py` 或跨 test 文件 import

### Requirement: Case layer import discipline

Case 文件 SHALL NOT import 其他 test 模块（`from tests.<domain>.test_* import ...`）。Case MAY import `tests.support.*` 与 `tests.conftest` re-export 的符号。`tests/unit/**` SHALL NOT import `tests.support` 或 `tests.conftest`。

#### Scenario: no cross-test-module imports

- **WHEN** 对 `tests/` 运行 grep 检查 `from tests\.(catalog|user|infra|health|ops)\.test_`
- **THEN** SHALL 无匹配

### Requirement: Assert-First and visible Act

Integration Case SHALL 以断言为主。被测 HTTP 行为（Act）SHALL 在 Case 内可见（inline `integration_client.*` 或 Act 型 helper 调用）。Act 的返回值 SHALL NOT 写入 Setup Context fixture。

#### Scenario: integration HTTP uses integration_client

- **WHEN** 审查带 `@pytest.mark.integration` 且发 HTTP 的 Case
- **THEN** SHALL 使用 `integration_client` fixture（或等价依赖 `db_session` override 的 client）
- **AND** SHALL NOT 仅用无 override 的 `client` 写库

#### Scenario: create product Act visible in case

- **WHEN** 审查 `test_create_product_success` 类用例
- **THEN** POST `/products` 或 `create_product` helper 调用 SHALL 出现在 Case 函数体内
- **AND** SHALL NOT 仅依赖 fixture 隐式完成该 POST

#### Scenario: Act result not in context

- **WHEN** 审查 Setup fixture 注入的 `*Context`
- **THEN** Context SHALL NOT 包含被测 Act 的 `*Result` 字段

### Requirement: Atomic helpers return typed Result without success assert

单次 HTTP helper SHALL 返回 `*Result`（含 `status_code`、`body: DomainResponse | None`）。SHALL NOT 在 helper 内 assert 成功状态码。SHALL NOT 接收或返回 `*Context`。

#### Scenario: register_user returns honest failure

- **WHEN** 调用 `register_user` 且 API 返回 422
- **THEN** helper SHALL 返回 `RegisterResult` 且 `status_code == 422`
- **AND** helper SHALL NOT raise 因 status 非 201

### Requirement: Fan-in orchestrator prerequisites in case scope

扇入 orchestrator 的前置数据 SHALL 保留在 Case 作用域（瘦身 `*Context`、显式 `access_token` 参数、fixture 依赖链或 Arrange 局部变量）。SHALL NOT 使用仅返 Act 结果的 one-shot 黑盒 helper 作为唯一前置来源。

#### Scenario: create product uses explicit context inputs

- **WHEN** 调用 `create_product(integration_client, shop_token=..., category=...)`
- **THEN** Case 或 fixture SHALL 仍持有 `shop_owner` / `admin_auth_headers` 等 Context
- **AND** 持久 ID（如 `product_id`）MAY 来自 Act 的 `*Result.body` 或 `tests/support/db` 查询

### Requirement: Setup fixture fail-fast

表示 happy-path 前置世界的 Setup fixture SHALL 在任一步失败时 `pytest.fail`（或 documented skip）。失败路径测试 SHALL 在 Case 内调用原子 helper，SHALL NOT 使用失败状态 Setup fixture。

#### Scenario: shop owner fixture fails on unsuccessful shop

- **WHEN** `register_and_open_shop` 返回的 `ShopResult.status_code != 201`
- **THEN** `shop_owner` fixture SHALL `pytest.fail`
- **AND** SHALL NOT 向 Case 注入失败状态的 Context

#### Scenario: login failure tested in case not fixture

- **WHEN** 测试密码错误登录
- **THEN** Case SHALL 调用 `login_user` 并 assert `status_code`
- **AND** SHALL NOT 依赖「错误密码 Context」fixture

### Requirement: Arrange versus Act boundary

除当前 Case 被测 API 外，所有 helper 与 fixture 执行均为 Arrange。Setup fixture SHALL NOT 替 Case 执行被测端点。

#### Scenario: fixture register and open shop is arrange

- **WHEN** Case 被测为 POST `/products`
- **THEN** fixture 内 `register_and_open_shop` SHALL 视为 Arrange
- **AND** fixture SHALL NOT 调用 `create_product` 作为 Setup

### Requirement: Simple GET Act may be inline

简单 GET 端点的 Act MAY 在 Case 内使用 `await integration_client.get(...)` 与 `model_validate`，不强制 action helper。

#### Scenario: public shop get inline

- **WHEN** 审查 `test_get_public_shop_*` 类用例
- **THEN** MAY 在 Case 内直接 `integration_client.get`
- **AND** SHALL 仍遵守 Act 在 Case 可见

### Requirement: Test directory layout for ops probes

Health、readiness、migration smoke 探针 SHALL 位于 `tests/ops/`。纯 JWT/DB 逻辑测试 MAY 保留在 `tests/infra/` 或 `tests/unit/`。

#### Scenario: ops directory contains health

- **WHEN** 审查运维探针测试
- **THEN** `tests/ops/test_health.py` SHALL 存在（自 `tests/health/` 迁入）

### Requirement: Enforcement tooling

项目 SHALL 对 `tests/` 启用 ruff ANN 规则。CI SHALL 包含 grep 检查禁止 test 模块互 import。

#### Scenario: ci rejects cross test import

- **WHEN** 某 test 文件新增 `from tests.catalog.test_create_product import ...`
- **THEN** CI grep step SHALL 失败

### Requirement: Bearer header projection without stored copies

Bearer 请求头 SHALL 通过纯函数 `bearer_headers(access_token: str)` 投影。Context 与 `*Result` SHALL NOT 含存储型拷贝 `headers` 字段。

#### Scenario: slim context holds token only

- **WHEN** 审查 refactor 后的 `ShopOwnerContext` / `AuthContext`
- **THEN** SHALL 主要含 `access_token: str`
- **AND** SHALL NOT 含 `root: PipelineResult`
- **AND** SHALL NOT 含 `headers: dict[str, str]` 存储型字段

### Requirement: Legacy anti-pattern documentation

refactor 前 SHALL 在 `docs/troubleshooting/测试架构-旧模式反模式记录.md` 记录旧架构反模式：每个反模式 SHALL 含真实代码片段、问题标注与应然方向；SHALL 覆盖 test 互 import、helper 内 assert、helper 返 Context、Context 嵌套/存储字段、fixture 不 fail-fast、test 内 DB seed 等；每个反模式 MAY 仅举 1–2 个最突出案例。

#### Scenario: troubleshooting doc explains create product anti-pattern

- **WHEN** 阅读 troubleshooting 文档中关于 test 内 helper 的章节
- **THEN** SHALL 含 `_create_product` 实现片段及 `from tests.catalog.test_create_product import` 互 import 示例
- **AND** SHALL 标明 helper 内 assert 201 与 Case 层重复 POST 的问题

#### Scenario: troubleshooting doc exists before catalog refactor

- **WHEN** 开始迁移 `tests/catalog/` 前
- **THEN** troubleshooting 文档 SHALL 已存在且可被 reviewer 对照迁移

### Requirement: Test environment via APP_ENV_FILE and dotenv test file

项目 SHALL 提供 `.env.test` 作为 integration/CI 测试环境配置。`app/infra/config.py` SHALL 通过环境变量 `APP_ENV_FILE` 选择 env 文件（默认 `.env`）。`task test` 与 CI SHALL 设置 `APP_ENV_FILE=.env.test`。

#### Scenario: task test loads env test

- **WHEN** 执行 `devbox run -- task test`
- **THEN** 进程环境 SHALL 含 `APP_ENV_FILE=.env.test`
- **AND** `get_settings()` SHALL 读取 `.env.test` 中的 `JWT_SECRET_KEY` 与 `DATABASE_URL`（CI 可用 env 覆盖 `DATABASE_URL`）

#### Scenario: helpers do not duplicate jwt constants

- **WHEN** grep `tests/support/` 中硬编码 `JWT_SECRET_KEY` 或 `configure_integration_test_env` duplicate 常量
- **THEN** SHALL 无匹配（env 加载迁出）

### Requirement: Settings cache lifecycle

`get_settings.cache_clear()` SHALL 仅出现在 `tests/support/utils.py`（或文档化的 env 模块）及 mutating fixture teardown。HTTP helper 与 atomic orchestrator SHALL NOT 调用 `cache_clear` 或 `ensure_integration_auth_env`。

#### Scenario: no cache clear in register helper

- **WHEN** 审查 `register_user` 等 atomic HTTP helper
- **THEN** SHALL NOT 调用 `reset_settings_cache` 或 `ensure_integration_auth_env`

#### Scenario: test auth module aligned after ensure removal

- **WHEN** 审查 `tests/infra/test_auth.py`
- **THEN** SHALL 与 `.env.test` / env 纪律一致，SHALL NOT 单独保留 obsolete ensure 调用

### Requirement: Integration transaction isolation via dependency override and SAVEPOINT

带 `@pytest.mark.integration` 且使用 HTTP 写库的测试 SHALL 通过 `db_session` fixture 注册 `app.dependency_overrides[get_db]`，使 HTTP 与 `tests/support/db` 共用同一 `AsyncSession`。`db_session` SHALL 使用外层事务 + SAVEPOINT（如 `join_transaction_mode="create_savepoint"`），使 service 内 `session.commit()` 不提交外层事务。测试 teardown SHALL 对外层事务 `rollback`，实现零数据残留。

#### Scenario: override registered in db session fixture

- **WHEN** `db_session` fixture yield 期间
- **THEN** `app.dependency_overrides[get_db]` SHALL 已注册
- **AND** override SHALL yield 同一测试 session 且不在请求结束时 close session

#### Scenario: poc rollback clears http data

- **WHEN** POC 用例经 `integration_client` 注册/开店后外层 rollback
- **THEN** 对应 users/shops 行 SHALL 不可再被同一测试外连接查到（或下一用例可重复固定 email）

#### Scenario: reset engine disposes app global engine only

- **WHEN** `_reset_global_database_engine` autouse 执行
- **THEN** `reset_engine()` SHALL dispose `app.infra.database` 模块级 engine
- **AND** SHALL NOT dispose `db_session` fixture 使用的测试 engine
- **AND** autouse SHALL 保留（非 SAVEPOINT 成功后移除）

### Requirement: integration_client versus client fixtures

项目 SHALL 提供 `client`（无 `get_db` override，供 health 等）与 `integration_client`（依赖 `db_session`，供 integration HTTP 业务测）。两者 SHALL 均为 `httpx.AsyncClient` 包装同一 `app`。

#### Scenario: health uses plain client

- **WHEN** 审查 `tests/ops/test_health.py` 或等价无 DB 写库探针
- **THEN** MAY 使用 `client` 且无 `db_session` 依赖

#### Scenario: ordering integration uses integration client

- **WHEN** 审查 `tests/ordering/` 下 `@integration` HTTP 用例
- **THEN** SHALL 使用 `integration_client`（或依赖链等价）

### Requirement: DB state assertion via tests support db

持久化状态断言（库存、订单 status 等）SHALL 经 `tests/support/db/` helper，使用与 override 相同的 `AsyncSession`。Case SHALL NOT 直接 import `app.*.repository`。SHALL NOT 为状态断言调用 service。

DB 断言是验证副作用的**主要路径**。HTTP GET SHALL 仅作为 Act（被测端点本身）保留，SHALL NOT 作为其他端点 Act 后的状态断言手段。同一事实的 HTTP GET 断言与 DB 断言 SHALL NOT 并存——DB 断言替代 HTTP GET，不追加。

#### Scenario: stock change asserted via db helper not http get

- **WHEN** 某测试的 Act 是 POST /orders 或 POST /orders/{id}/cancel 等写操作
- **THEN** 库存变化的断言 SHALL 使用 `tests/support/db/catalog.py` 的 `get_product_stock`
- **AND** SHALL NOT 再通过 `GET /products/{id}` 验证同一库存变化

#### Scenario: order status change asserted via db helper not http get

- **WHEN** 某测试的 Act 是 POST /orders/{id}/pay 或 POST /orders/{id}/cancel 等写操作
- **THEN** 订单 status 变化的断言 SHALL 使用 `tests/support/db/ordering.py` 的 `get_order_status`
- **AND** SHALL NOT 再通过 `GET /orders/{id}` 仅为验证 status 变化而发 HTTP 请求

#### Scenario: lazy release asserts stock via db helper

- **WHEN** 懒释放 integration 用例断言库存还原
- **THEN** SHALL 使用 `tests/support/db/catalog.py` 的 `get_product_stock` 查询 stock
- **AND** SHALL NOT 附带 `GET /products/{id}` HTTP 调用做同一库存验证

#### Scenario: case does not import app repository

- **WHEN** grep `tests/**/test_*.py` 中 `from app\..*\.repository`
- **THEN** SHALL 无匹配

### Requirement: DB seed for domain data arrange

Shop / Category / Product / Order 的 Arrange SHALL 经 `tests/support/db/` seed helper（直写 SAVEPOINT session，不经 HTTP）。例外：conftest fixture 中的 auth token 生成走 HTTP（身份逻辑不重复）。

#### Scenario: ordering test arranges shop and product via db seed

- **WHEN** 审查 ordering 域 integration 测试的 Arrange 阶段
- **THEN** shop / category / product 的创建 SHALL 使用 `tests/support/db/catalog.py` 的 `seed_shop`、`seed_category`、`seed_product`
- **AND** SHALL NOT 通过 `POST /shops`、`POST /categories`、`POST /products` HTTP 端点铺设 Arrange 数据

#### Scenario: seed helpers use same session as integration client

- **WHEN** 审查 `tests/support/db/` 下的 seed 函数签名
- **THEN** SHALL 接收 `AsyncSession` 参数（测试的 `db_session`）
- **AND** SHALL 通过 `session.flush()` 使数据对同一事务内的 HTTP Act 可见
- **AND** SHALL NOT 创建独立 engine 或 commit 到事务外

### Requirement: Lazy expire tests use backdate not ttl env override

ordering 懒释放 integration 测 SHALL 通过 `tests/support/db` backdate `orders.expires_at` 到过去触发过期，SHALL NOT 依赖 `override_order_reservation_ttl`、`wait_past_order_expiry` 或修改 `ORDER_RESERVATION_TTL_SECONDS` 环境变量。生产 `ordering.service` SHALL NOT 含 `os.environ.get("ORDER_RESERVATION_TTL_SECONDS")` 分支。

#### Scenario: no ttl or wait helpers after migration

- **WHEN** grep `tests/` 中 `override_order_reservation_ttl` 或 `wait_past_order_expiry`
- **THEN** SHALL 无匹配

#### Scenario: lazy release test backdates expires at

- **WHEN** 审查 lazy release Case
- **THEN** SHALL 在 HTTP GET 触发懒释放前调用 backdate helper
- **AND** SHALL NOT 使用 sleep/wait 等待 TTL 过期作为主触发手段

### Requirement: Seed inactive user uses shared db session

`seed_inactive_user` SHALL 接受 `AsyncSession` 并在同一测试事务内插入，SHALL NOT 使用独立 engine 并 commit 到事务外。调用方 SHALL 运行在 SAVEPOINT / `integration_client` 作用域内。

#### Scenario: seed uses session not database url engine

- **WHEN** 审查 `tests/support/seeds.py`
- **THEN** `seed_inactive_user` SHALL NOT 调用 `create_async_engine(database_url)`

#### Scenario: seed call sites use integration scope

- **WHEN** 审查 `tests/user/test_login.py` 与 `tests/ordering/test_create_order_by_seller.py`
- **THEN** SHALL 注入 `db_session` 或 `integration_client` 作用域内调用 `seed_inactive_user(session, ...)`
- **AND** SHALL NOT 仅传 `database_url` 与无 override 的 `client`

### Requirement: Integration probe exceptions without savepoint override

下列测试 SHALL NOT 要求 `integration_client` / `get_db` override，SHALL 在 design 中文档化：

- `tests/catalog/test_admin_seed.py`（子进程 alembic + 独立 engine）
- `tests/ops/test_readiness.py`（readiness 独立 ping）
- `tests/user/test_user_summary.py`（纯 service + rollback `db_session`）

#### Scenario: admin seed test remains independent

- **WHEN** 审查 `test_migration_seed_admin_exists`
- **THEN** MAY 继续使用 `database_url` 与独立 `create_async_engine`
- **AND** SHALL NOT 被强制改为 SAVEPOINT 模式

### Requirement: Unique builders retained within test

`unique_email`、`unique_shop_name` 等 builders SHALL 保留，用于单测内创建多个不冲突实体。本 change SHALL NOT 引入测间固定 email 复用作为隔离手段。

#### Scenario: two users in one test use unique emails

- **WHEN** 单测内注册两个不同用户
- **THEN** SHALL 使用 `unique_email()` 或等价保证 email 不同

### Requirement: SAVEPOINT proof of concept gate

全量删除 `PipelineResult` 与 §5 单批测试迁移 SHALL NOT 早于 SAVEPOINT POC 用例 CI 通过。

#### Scenario: poc task completes before section five migration

- **WHEN** 审查 `tasks.md` 执行顺序
- **THEN** Task 3.0 SHALL 标记在 §5 之前

#### Scenario: each test file touched once in section five

- **WHEN** §5 执行完成
- **THEN** 每个 integration 测试文件 SHALL 在同一节内完成 `integration_client`、Context 瘦身与 Pipeline 删除，SHALL NOT 依赖 §4 与 §5 分两批改同一文件
