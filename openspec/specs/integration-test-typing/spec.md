# integration-test-typing

## Purpose

integration 测试 support 层约定：用 domain Pydantic schema 构造合法请求（builders）、Setup Context（fixture 返回值）与 ActionResult（HTTP helper 返回值）替代 `dict[str, Any]`；测试专用字段（`headers`、`status_code` 等）SHALL 仅存在于 `tests/`，不污染 `app/*/schemas.py`。

## Requirements

### Requirement: Domain schema builders for test data

测试 support 层 SHALL 提供 `build_*` 函数（位于 `tests/support/builders.py`），用于构造 **合法** 的 domain request schema（如 `RegisterRequest`、`ShopCreate`、`ProductCreate`）。函数 SHALL 返回 `app/*/schemas.py` 中定义的 Pydantic 模型，并在构造时执行 Pydantic 校验。

#### Scenario: build_shop_create 返回可用 ShopCreate

- **WHEN** 测试调用 `build_shop_create()` 且未传入非法字段
- **THEN** 返回值 SHALL 为 `ShopCreate` 实例
- **AND** 该实例 SHALL 可通过 `model_dump(mode="json")` 用于 `client.post` 请求体

#### Scenario: 非法字段在 build 时失败

- **WHEN** 测试调用 `build_product_create(stock=0, ...)` 且违反 schema 约束
- **THEN** 构造 SHALL 在发出 HTTP 请求之前抛出校验错误

### Requirement: Setup Context for fixtures

Setup fixture（如 `authenticated_user`、`shop_owner`、`admin_auth_headers`）SHALL 返回 `tests/support/contexts.py` 中定义的 `@dataclass` Context 类型。Context SHALL 为极薄容器，主字段为 `root: PipelineResult`（fail-fast 后的顺序链）。Context SHALL NOT 使用嵌套 Context 作为主模型（如 `ShopOwnerContext.auth: AuthContext`）。Context SHALL NOT 含存储型便利字段拷贝（如初始化后不与 Pipeline 同步的 `headers` dict）。多步前置状态 SHALL 通过 `context.root.step(ResultType)` 访问。

#### Scenario: shop owner context exposes pipeline root

- **WHEN** integration 测试注入 `shop_owner` fixture 且 Setup 成功
- **THEN** `shop_owner` SHALL 为 `ShopOwnerContext` 类型
- **AND** `shop_owner.root` SHALL 为 `PipelineResult`
- **AND** `shop_owner.root.step(ShopResult).body` SHALL 可用于店铺断言

#### Scenario: register step accessible via pipeline

- **WHEN** Case 需要店主 Bearer token
- **THEN** SHALL 通过 `shop_owner.root.step(RegisterResult)` 取得 `RegisterResult`
- **AND** SHALL 使用 `bearer_headers(...)` 或等价纯函数生成 Authorization 头

#### Scenario: shop owner fixture fail fast

- **WHEN** `shop_owner` fixture 执行 Setup 且 `ShopResult.status_code != 201`
- **THEN** fixture SHALL `pytest.fail`
- **AND** SHALL NOT 注入含失败 `ShopResult` 的 Context 供 Case 继续使用

### Requirement: ActionResult for HTTP helpers

可复用 HTTP helper（如 `register_user`、`login_user`、`create_category`）SHALL 返回 `tests/support/results.py` 中定义的 Result dataclass。线性组合 orchestrator（如 `register_and_open_shop`）SHALL 返回 `PipelineResult` 而非 `*Context`。Helper SHALL NOT 返回 `*Context`。Result SHALL 包含 `status_code` 与 `body: XxxResponse | None`；非 2xx 时 `body` SHALL 为 `None`。Helper SHALL NOT 在内部 assert 成功状态码。

#### Scenario: register user success returns typed body

- **WHEN** 测试调用 `register_user` 且 API 返回 201 与合法 JSON
- **THEN** 返回值 SHALL 为 `RegisterResult`
- **AND** `result.body` SHALL 为 `TokenResponse` 实例

#### Scenario: register user business failure body is none

- **WHEN** 测试调用 `register_user` 且 API 返回 422
- **THEN** `result.status_code` SHALL 为 422
- **AND** `result.body` SHALL 为 `None`

#### Scenario: register and open shop returns pipeline not context

- **WHEN** 调用 `register_and_open_shop(client)`
- **THEN** 返回值 SHALL 为 `PipelineResult`
- **AND** SHALL NOT 为 `ShopOwnerContext`

### Requirement: No domain schema pollution

测试 typing 结构（Context、Result）SHALL 仅存在于 `tests/` 目录。系统 SHALL NOT 为测试目的向 `app/*/schemas.py` 添加 `headers`、`status_code` 或 httpx 相关字段。

#### Scenario: 业务 schema 文件无测试字段

- **WHEN** 审查 `app/user/schemas.py` 与 `app/catalog/schemas.py`
- **THEN** SHALL NOT 出现测试专用字段或 httpx 类型依赖

### Requirement: Integration tests use typed assertions

已迁移的 user/catalog integration 测试 SHALL 使用 Context/Result/`PipelineResult.step` 属性访问或 `model_validate` 解析响应。店铺 id 等断言 SHALL 使用 `shop_owner.root.step(ShopResult).body.id` 等路径（在 body 非 None 前提下），SHALL NOT 依赖已废弃的 `shop_owner.shop.id` 存储字段（refactor 完成后）。

#### Scenario: shop id assertion uses pipeline step

- **WHEN** 测试比较响应中的 shop id 与 fixture 中的 shop id
- **THEN** 测试代码 SHALL 使用 `shop_owner.root.step(ShopResult).body.id` 或等价 `step` 路径

### Requirement: Format boundaries belong to schema unit tests

DTO 格式/字段级非法输入（如 password 长度、`ProductCreate` 空 `category_ids`、primary 不在列表）SHALL 在 `tests/unit/{domain}/test_{domain}_schema.py` 中测试。Integration 测试 SHALL NOT 重复上述格式的 HTTP 422 用例。Integration 仍 SHALL 覆盖业务规则导致的 422（如重复邮箱、closed shop 下创建商品）。

#### Scenario: no duplicate password length HTTP test in integration

- **WHEN** 实现本 change 后审查 `tests/user/test_register.py`
- **THEN** SHALL NOT 存在仅断言 password 长度导致 HTTP 422 的 integration 用例
- **AND** 对应校验 SHALL 存在于 `tests/unit/user/test_user_schema.py`

#### Scenario: no duplicate product category format HTTP test in integration

- **WHEN** 实现本 change 后审查 `tests/catalog/test_create_product.py`
- **THEN** SHALL NOT 存在仅断言 `category_ids` 格式/组合导致 HTTP 422 的 integration 用例（空列表、primary 不在列表）
- **AND** 对应校验 SHALL 存在于 `tests/unit/catalog/test_catalog_schema.py`
