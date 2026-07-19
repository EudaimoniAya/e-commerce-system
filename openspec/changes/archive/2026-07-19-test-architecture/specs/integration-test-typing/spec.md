## MODIFIED Requirements

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

### Requirement: Integration tests use typed assertions

已迁移的 user/catalog integration 测试 SHALL 使用 Context/Result/`PipelineResult.step` 属性访问或 `model_validate` 解析响应。店铺 id 等断言 SHALL 使用 `shop_owner.root.step(ShopResult).body.id` 等路径（在 body 非 None 前提下），SHALL NOT 依赖已废弃的 `shop_owner.shop.id` 存储字段（refactor 完成后）。

#### Scenario: shop id assertion uses pipeline step

- **WHEN** 测试比较响应中的 shop id 与 fixture 中的 shop id
- **THEN** 测试代码 SHALL 使用 `shop_owner.root.step(ShopResult).body.id` 或等价 `step` 路径
