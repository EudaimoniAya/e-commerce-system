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

Setup fixture（如 `authenticated_user`、`shop_owner`、`admin_auth_headers`）SHALL 返回 `tests/support/contexts.py` 中定义的 `@dataclass` Context 类型，而非 `dict[str, Any]`。Context SHALL 组合 domain schema 字段（如 `TokenResponse`、`ShopResponse`）与测试专用字段（如 `headers`、`status_code`）。多步骤 fixture SHALL 使用嵌套 Context 表达前置步骤（如 `ShopOwnerContext.auth`）。

#### Scenario: shop_owner fixture 提供 typed 店铺与 headers

- **WHEN** integration 测试注入 `shop_owner` fixture 且前置步骤成功
- **THEN** `shop_owner` SHALL 为 `ShopOwnerContext` 类型
- **AND** `shop_owner.headers` SHALL 可用于已认证 HTTP 请求
- **AND** `shop_owner.shop` SHALL 为 `ShopResponse` 或 `None`（与步骤成败一致）

#### Scenario: ShopOwnerContext 主步骤 status 指开店

- **WHEN** 测试断言 `shop_owner.status_code`
- **THEN** 该值 SHALL 表示 POST `/shops` 的 HTTP 状态码
- **AND** 注册步骤状态 SHALL 通过 `shop_owner.auth.status_code` 访问

### Requirement: ActionResult for HTTP helpers

可复用 HTTP helper（如 `register_user`、`login_user`、`create_category`）SHALL 返回 `tests/support/results.py`（或等价位置）中定义的 Result dataclass，而非 `dict[str, Any]`。Result SHALL 包含 `status_code` 与 `body: XxxResponse | None`；非 2xx 时 `body` SHALL 为 `None`。

#### Scenario: register_user 成功返回 typed body

- **WHEN** 测试调用 `register_user` 且 API 返回 201 与合法 JSON
- **THEN** 返回值 SHALL 为 `RegisterResult`（或等价命名）
- **AND** `result.body` SHALL 为 `TokenResponse` 实例

#### Scenario: register_user 业务失败时 body 为 None

- **WHEN** 测试调用 `register_user` 且 API 返回 422（如重复邮箱）
- **THEN** `result.status_code` SHALL 为 422
- **AND** `result.body` SHALL 为 `None`

### Requirement: No domain schema pollution

测试 typing 结构（Context、Result）SHALL 仅存在于 `tests/` 目录。系统 SHALL NOT 为测试目的向 `app/*/schemas.py` 添加 `headers`、`status_code` 或 httpx 相关字段。

#### Scenario: 业务 schema 文件无测试字段

- **WHEN** 审查 `app/user/schemas.py` 与 `app/catalog/schemas.py`
- **THEN** SHALL NOT 出现测试专用字段或 httpx 类型依赖

### Requirement: Integration tests use typed assertions

已迁移的 user/catalog integration 测试 SHALL 使用 Context/Result 属性访问或 `model_validate` 解析响应，SHALL NOT 依赖 `result["json"]` 或 `fixture["headers"]` 字典下标访问。

#### Scenario: 店铺 id 断言使用属性

- **WHEN** 测试比较响应中的 shop id 与 fixture 中的 shop id
- **THEN** 测试代码 SHALL 使用 `shop_owner.shop.id` 等属性路径（在 `shop` 非 None 前提下）

### Requirement: Format boundary HTTP tests deferred

下列格式边界 integration 用例在本 change SHALL 保留且仅最小改动（TODO 注释），完整迁移至 schema 单测 SHALL 由后续 `test-schema-unit-tests` change 完成：

- `test_register_password_too_short_returns_422`
- `test_register_password_too_long_returns_422`
- `test_create_product_empty_category_ids_returns_422`
- `test_create_product_invalid_primary_category_returns_422`

#### Scenario: 格式用例保留 TODO 标记

- **WHEN** 实现本 change
- **THEN** 上述 4 个测试 SHALL 仍存在于原模块
- **AND** SHALL 带有指向 `test-schema-unit-tests` 的 TODO 注释
