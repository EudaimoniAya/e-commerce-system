## ADDED Requirements

### Requirement: App layer discipline refactor preserves external behavior

本 change 对 `app/catalog`、`app/ordering`、`app/support`、`app/user` 的内部 refactor（deps 两大类、current-object 鉴权收编、deps 命名统一 `get_current_*`）SHALL **不改变**既有 HTTP API 的路径、请求/响应 JSON schema 及业务语义（与 `openspec/specs/catalog-*`、`openspec/specs/ordering-*`、`openspec/specs/support-conversations`、`openspec/specs/user-auth` 中已归档 Scenario 一致）。

#### Scenario: Full test suite passes after each Phase

- **WHEN** 开发者完成任一 Phase 并执行 `devbox run -- task ci`（须先 `db:up`、`migrate`、`redis:up`）
- **THEN** pytest SHALL 全绿且与 refactor 前相同数量的用例通过
- **AND** `task format:check`、`task ruff`、`task check-test-imports` SHALL 通过

#### Scenario: Catalog flows unchanged for clients

- **WHEN** 客户端调用既有 catalog 端点（店主商品 CRUD、本店商品列表、店铺资料、类目列表，与 refactor 前相同的请求体与 JWT）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致

#### Scenario: Ordering flows unchanged for clients

- **WHEN** 客户端调用既有 ordering 端点（下单、支付、发货、取消、买家/店主订单列表、batch-pay）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致
- **AND** 例外（design Decision 4c 归属失败统一 404）：`pay_order` 非买家、`create_shipment` 非本店店主由 403 统一为 404（不泄漏存在性；断言见 `tests/ordering/test_pay_order.py` / `test_shipments_and_receipt.py`）

#### Scenario: Cart flows unchanged for clients

- **WHEN** 客户端调用既有 cart 端点（加购、列表、改数量、删除、checkout、checkout-batch 详情）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致

#### Scenario: Support flows unchanged for clients

- **WHEN** 客户端调用既有 support 端点（买家发消息/查会话、店主 inbox/回复）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致

#### Scenario: User flows unchanged for clients

- **WHEN** 客户端调用既有 user 端点（GET/PATCH /users/me）
- **THEN** 响应 status code 与 response body 结构 SHALL 与 refactor 前一致

### Requirement: App layer discipline is enforced by lint gate

本 change 收尾新增的 `scripts/check_app_layer_discipline.py` SHALL 在 `task ci` 中执行，强制执行以下层纪律：`_*` 私有名不跨模块、跨域 import 白名单（service 接口 + schemas）、`get_current_*` 仅被本域 router 消费。

#### Scenario: Lint gate catches cross-domain private import

- **WHEN** `app/` 任一模块跨域 import 对方 `_*` 私有名（如 `from app.catalog.shop_service import _to_shop_response`）
- **THEN** `check_app_layer_discipline.py` SHALL 报错且 `task ci` 失败

#### Scenario: Lint gate catches cross-domain model import

- **WHEN** `app/` 任一模块跨域 import 对方 ORM model 或 repository
- **THEN** `check_app_layer_discipline.py` SHALL 报错且 `task ci` 失败

#### Scenario: Lint gate allows intra-domain and whitelisted imports

- **WHEN** `app/` 模块做域内 import（如 `from app.catalog.models import Shop`），或跨域 import 对方 service 接口 / schemas / service-provider deps
- **THEN** `check_app_layer_discipline.py` SHALL 放行，不报错

#### Scenario: Lint gate catches current-object deps escaping domain

- **WHEN** 任一 `get_current_*` deps 被本域 router 之外的模块 import
- **THEN** `check_app_layer_discipline.py` SHALL 报错且 `task ci` 失败
