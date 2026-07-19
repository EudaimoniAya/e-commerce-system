# test-architecture

## Purpose

测试代码四层架构与数据流纪律：Case（Assert-First）、Fixture（fail-fast Context 注入）、Support（helper + PipelineResult + builders/results）、Utilities（纯函数）。确保 Arrange/Act 边界清晰、helper 不污染 test 文件、组合步骤可维护。

## ADDED Requirements

### Requirement: Four-layer test architecture

测试代码 SHALL 分为 Case、Fixture、Support、Utilities 四层。Case 层位于 `tests/**/test_*.py`；Fixture 层位于 `tests/conftest.py`；Support 层位于 `tests/support/`；Utilities 为 Support 内无 HTTP/DB 的纯函数。

#### Scenario: Case layer contains only test functions

- **WHEN** 审查 `tests/user/` 或 `tests/catalog/` 下 `test_*.py`
- **THEN** SHALL 仅含 `test_*` 函数与允许的模块级常量
- **AND** SHALL NOT 含可复用的 HTTP helper 或 DB seed 函数

#### Scenario: Support layer owns HTTP helpers

- **WHEN** 测试需要可复用 HTTP 调用
- **THEN** helper SHALL 位于 `tests/support/`（如 `helpers.py`）
- **AND** SHALL NOT 位于 `test_*.py` 或跨 test 文件 import

### Requirement: Case layer import discipline

Case 文件 SHALL NOT import 其他 test 模块（`from tests.<domain>.test_* import ...`）。Case MAY import `tests.support.*` 与 `tests.conftest`  re-export 的符号。`tests/unit/**` SHALL NOT import `tests.support` 或 `tests.conftest`。

#### Scenario: no cross-test-module imports

- **WHEN** 对 `tests/` 运行 grep 检查 `from tests\.(catalog|user|infra|health|ops)\.test_`
- **THEN** SHALL 无匹配

### Requirement: Assert-First and visible Act

Integration Case SHALL 以断言为主。被测 HTTP 行为（Act）SHALL 在 Case 内可见（inline `client.*` 或 Act 型 helper 调用）。Act 的返回值 SHALL NOT 写入 Setup Context fixture。

#### Scenario: create product Act visible in case

- **WHEN** 审查 `test_create_product_success` 类用例
- **THEN** POST `/products` 或 `create_product` helper 调用 SHALL 出现在 Case 函数体内
- **AND** SHALL NOT 仅依赖 fixture 隐式完成该 POST

#### Scenario: Act result not in context

- **WHEN** 审查 Setup fixture 注入的 `*Context`
- **THEN** Context SHALL NOT 包含被测 Act 的 `*Result` 字段

### Requirement: PipelineResult as sole composition container

顺序多步 orchestrator SHALL 返回 `PipelineResult`，其字段为 `steps: tuple[ActionResult, ...]`。SHALL NOT 使用 ad-hoc 组合 dataclass 命名字段（如 `OpenShopResult(register=, shop=)`）作为规范 API。

#### Scenario: register and open shop returns pipeline

- **WHEN** 调用 `register_and_open_shop(client)`
- **THEN** 返回值 SHALL 为 `PipelineResult`
- **AND** `pipeline.step(RegisterResult)` 与 `pipeline.step(ShopResult)` SHALL 可访问各步结果

#### Scenario: pipeline step uses exact type match

- **WHEN** 调用 `PipelineResult.step(RegisterResult)`
- **THEN** 实现 SHALL 使用 `type(step) is RegisterResult` 匹配
- **AND** 0 个或多个匹配时 `step()` SHALL raise `LookupError`

#### Scenario: pipeline all returns matching steps

- **WHEN** 调用 `PipelineResult.all(ProductResult)` 且 steps 中含多个 `ProductResult`
- **THEN** SHALL 返回包含全部匹配项的 tuple

### Requirement: Atomic helpers return typed Result without success assert

单次 HTTP helper SHALL 返回 `*Result`（含 `status_code`、`body: DomainResponse | None`）。SHALL NOT 在 helper 内 assert 成功状态码。SHALL NOT 接收或返回 `*Context`。

#### Scenario: register_user returns honest failure

- **WHEN** 调用 `register_user` 且 API 返回 422
- **THEN** helper SHALL 返回 `RegisterResult` 且 `status_code == 422`
- **AND** helper SHALL NOT raise 因 status 非 201

### Requirement: Fan-in orchestrator prerequisites in case scope

扇入 orchestrator 的前置数据 SHALL 保留在 Case 作用域（fixture `Context.root`、显式参数或 Arrange 局部变量）。SHALL NOT 使用仅返 Act 结果的 one-shot 黑盒 helper 作为唯一前置来源。

#### Scenario: create product uses explicit pipeline inputs

- **WHEN** 调用 `create_product(client, shop_owner=pipeline, category=category_result)`
- **THEN** Case 或 fixture SHALL 仍持有 `shop_owner` / `admin_auth` 等 Pipeline 引用
- **AND** 断言 shop_id 时 SHALL 可通过 `shop_owner.step(ShopResult)` 取得

### Requirement: Setup fixture fail-fast

表示 happy-path 前置世界的 Setup fixture SHALL 在任一步失败时 `pytest.fail`（或 documented skip）。失败路径测试 SHALL 在 Case 内调用原子 helper，SHALL NOT 使用失败状态 Setup fixture。

#### Scenario: shop owner fixture fails on unsuccessful shop

- **WHEN** `register_and_open_shop` 返回的 Pipeline 中 `ShopResult.status_code != 201`
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

简单 GET 端点的 Act MAY 在 Case 内使用 `await client.get(...)` 与 `model_validate`，不强制 action helper。

#### Scenario: public shop get inline

- **WHEN** 审查 `test_get_public_shop_*` 类用例
- **THEN** MAY 在 Case 内直接 `client.get`
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

Bearer 请求头 SHALL 通过纯函数（如 `bearer_headers(result)`）从 `*Result` 投影。Context 与 `*Result` SHALL NOT 含存储型拷贝 `headers` 字段（初始化后不与 body 同步的 dict）。

#### Scenario: no stored headers on new context

- **WHEN** 审查 refactor 后的 `ShopOwnerContext`
- **THEN** SHALL 仅含 `root: PipelineResult`（及文档化字段）
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
