## ADDED Requirements

### Requirement: App layer refactor preserves external behavior

本 change 对 `app/ordering` 与 `app/catalog` 的内部 refactor SHALL **不改变**既有 HTTP API 的路径、请求/响应 JSON schema 及业务语义（与 `openspec/specs/ordering-*`、`openspec/specs/catalog-*` 中已归档 Scenario 一致）。

#### Scenario: Full test suite passes after each Phase

- **WHEN** 开发者完成 Phase A 或 Phase B 并执行 `devbox run -- task ci`（须先 `db:up`、`migrate`、`redis:up`）
- **THEN** pytest SHALL 全绿且与 refactor 前相同数量的用例通过
- **AND** `task format:check`、`task ruff`、`task check-test-imports` SHALL 通过

#### Scenario: Ordering seller flows unchanged for clients

- **WHEN** 客户端调用卖家建单、发货、本店订单列表等既有 ordering 端点（与 Phase A 前相同的请求体与 JWT）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致

#### Scenario: Catalog public and shop owner flows unchanged for clients

- **WHEN** 客户端调用类目列表、商品 CRUD、店铺资料等既有 catalog 端点（与 Phase B 前相同）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致
