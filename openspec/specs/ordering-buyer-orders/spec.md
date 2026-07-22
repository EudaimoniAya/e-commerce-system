# ordering-buyer-orders

## Purpose

ordering 域买家发起订单垂直切片：同店多行下单、库存预留/释放、支付桩、发货、确认收货与取消；`orders`、`order_items` 两表（migration `005`；`initiated_by` 由 migration `006` 追加）；超时懒释放（`ORDER_RESERVATION_TTL_SECONDS`），含订单列表路径。

## Requirements

### Requirement: HTTP 422 vs 409 convention

系统在业务错误状态码上 SHALL 区分 **422** 与 **409**（与 user/catalog 既有用法对齐，全项目一致）：

- **422**：请求体形态可被接受，但相对业务语义或外部约束不成立，因而**无法创建或按规则写入**（失败不落在「对已存在目标资源做非法生命周期动作」上）。ordering 下单侧包括但不限于：跨店商品、库存不足、商品未上架、店铺非 `active`。对已存在资源的 PATCH/写入若因外部约束失败（如店名占用、closed 禁写），亦为 **422**。
- **409**：URL（或等价标识）指向的**资源已存在**，但当前生命周期状态**拒收该动作**（非法状态迁移、重复 pay、对 `completed`/`cancelled` 再 cancel、过期后对已终态化订单再 pay 等）。

认证/授权失败仍分别为 **401** / **403**，不适用本条。

#### Scenario: 建单业务约束失败使用 422

- **WHEN** `POST /orders` 因跨店、库存不足、未上架或店铺非 `active` 而失败
- **THEN** 响应状态码 SHALL 为 422（SHALL NOT 使用 409）

#### Scenario: 对已存在订单的非法动作使用 409

- **WHEN** 客户端对已存在订单请求当前 `status` 不允许的 pay、shipments、confirm-receipt 或 cancel
- **THEN** 响应状态码 SHALL 为 409（SHALL NOT 使用 422）

### Requirement: Orders and order items tables

系统 SHALL 在 **ordering 域** 拥有 `orders` 与 `order_items` 表（migration `005`；`initiated_by` 由 migration `006` 追加）。订单 SHALL 通过 `buyer_user_id`、`shop_id` 关联用户与店铺（仅存 FK 字段，SHALL NOT 声明跨域 SQLAlchemy relationship）。订单行 SHALL 在创建时快照 `product_name`、`unit_price`、`qty`。

#### Scenario: 订单表包含必需字段

- **WHEN** 查询 `orders` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`buyer_user_id`、`shop_id`、`status`、`cancel_reason`（可空）、`total_amount`、`expires_at`、`initiated_by`（`buyer` \| `seller`）、`created_at`、`updated_at`

#### Scenario: 订单行包含快照字段

- **WHEN** 查询 `order_items` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`、`order_id`、`product_id`、`product_name`、`unit_price`、`qty`

#### Scenario: 已有订单 initiated_by 回填 buyer

- **WHEN** migration `006` 执行至 head
- **THEN** 既有订单行的 `initiated_by` SHALL 为 `buyer`

### Requirement: Order status finite state machine

系统 SHALL 使用订单状态：`awaiting_payment`、`confirmed`、`shipped`、`completed`、`cancelled`。合法迁移 SHALL 为：`awaiting_payment`→`confirmed`（pay）、`confirmed`→`shipped`（shipments）、`shipped`→`completed`（confirm-receipt）；以及从 `awaiting_payment`/`confirmed`/`shipped`→`cancelled`（cancel 或超时）。非法迁移 SHALL 返回 **409**。

#### Scenario: 非法状态迁移返回 409

- **WHEN** 客户端对 `completed` 或 `cancelled` 订单请求 pay、shipments、confirm-receipt 或 cancel
- **THEN** 响应状态码 SHALL 为 409

### Requirement: Buyer creates multi-item order for one shop

系统 SHALL 提供 `POST /orders`（需认证）。请求体 SHALL 为 `{ "items": [ { "product_id", "qty" }, ... ] }`，至少一行；`qty` SHALL **≥ 1**。同一订单内所有商品 SHALL 属于同一店铺。成功时 SHALL 创建 `status=awaiting_payment`、`initiated_by=buyer` 的订单，设置 `expires_at`，计算 `total_amount` 为各行快照单价×数量之和，并通过 **catalog.service** 预留库存；响应 **201**。

#### Scenario: 创建订单成功

- **WHEN** 买家对同一 active 店铺下多个已上架且库存充足的商品提交合法 `POST /orders`
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 SHALL 含 `status` 为 `awaiting_payment`、`initiated_by` 为 `buyer`、订单行快照字段与 `expires_at`
- **AND** 对应商品可售库存 SHALL 已按 qty 减少

#### Scenario: 跨店商品返回 422

- **WHEN** 买家提交的 `items` 中商品属于不同店铺
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单
- **AND** 库存 SHALL NOT 被扣减

#### Scenario: 库存不足不建单

- **WHEN** 任一行 `qty` 超过当前可售库存
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单
- **AND** 所有商品库存 SHALL 保持扣减前的值（事务回滚）

#### Scenario: 未上架或店铺非 active 不可下单

- **WHEN** 商品未 `is_published` 或所属店铺非 `active`
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单

#### Scenario: 店主购买本店商品返回 403

- **WHEN** 认证用户为本店 `owner_user_id` 且请求购买该店商品
- **THEN** 响应状态码 SHALL 为 403
- **AND** SHALL NOT 创建订单

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /orders`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Payment stub confirms order

系统 SHALL 提供 `POST /orders/{id}/pay`（需认证，仅买家本人）。在 `status=awaiting_payment` 且未过期时，支付桩 SHALL **永远成功**，将状态迁移为 `confirmed`，响应 **200**；SHALL NOT 再次扣减库存。

#### Scenario: 支付桩成功

- **WHEN** 买家对本人的 `awaiting_payment` 且未过期订单请求 `POST /orders/{id}/pay`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 订单 `status` SHALL 为 `confirmed`
- **AND** 库存 SHALL 相对支付前不再减少

#### Scenario: 非买家支付返回 403

- **WHEN** 非该订单 `buyer_user_id` 的用户请求 pay
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 重复支付返回 409

- **WHEN** 买家对已 `confirmed`（或非 awaiting_payment）订单再次 pay
- **THEN** 响应状态码 SHALL 为 409

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /orders/{id}/pay`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Reservation expiry via lazy release

系统 SHALL 在创建订单时设置 `expires_at = now + ORDER_RESERVATION_TTL_SECONDS`（可配置，默认 86400 秒）。超时订单 SHALL 终态为 `cancelled` 且 `cancel_reason=expired`。本 change SHALL **仅**通过懒释放实现：在 pay、读取订单详情、**订单列表**（`GET /orders` 与 `GET /shops/me/orders`）等路径检查过期；SHALL NOT 依赖 Redis、MQ 或周期扫描。释放库存前 SHALL 使用条件更新：`UPDATE ... WHERE status='awaiting_payment'`，仅当影响行数为 1 时调用 catalog 释放库存。

#### Scenario: 过期后支付失败且库存还原

- **WHEN** 订单处于 `awaiting_payment` 且当前时间 ≥ `expires_at`
- **AND** 买家请求 `POST /orders/{id}/pay`（或触发懒释放的读路径后再观察库存）
- **THEN** 订单 SHALL 变为 `cancelled` 且 `cancel_reason=expired`（若尚未被释放）
- **AND** pay 响应状态码 SHALL 为 409（若请求为 pay）
- **AND** 预留库存 SHALL 已加回

#### Scenario: 短 TTL 可测

- **WHEN** 测试将 `ORDER_RESERVATION_TTL_SECONDS` 设为较短值（如 10）并创建订单，等待超过 TTL 后触发懒释放
- **THEN** 库存 SHALL 还原为下单前数量

#### Scenario: 列表路径触发懒释放

- **WHEN** 买家请求 `GET /orders` 或店主请求 `GET /shops/me/orders`，且列表中含 `awaiting_payment` 且已过期订单
- **THEN** 系统 SHALL 对该订单执行懒释放（`cancelled` + `expired` + 库存加回）

### Requirement: Seller creates shipment

系统 SHALL 提供 `POST /orders/{id}/shipments`（需认证，仅订单所属店铺店主）。请求体 SHALL 允许空对象 `{}` 或可选 `note`；SHALL NOT 要求物流单号。成功时 SHALL 将 `confirmed` 订单迁移为 `shipped`，响应 **201**。

#### Scenario: 卖家发货成功

- **WHEN** 本店店主对 `confirmed` 订单请求 `POST /orders/{id}/shipments` 且 body 为 `{}`
- **THEN** 响应状态码 SHALL 为 201
- **AND** 订单 `status` SHALL 为 `shipped`

#### Scenario: 非店主发货返回 403

- **WHEN** 非本店店主请求 shipments
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 非 confirmed 发货返回 409

- **WHEN** 店主对非 `confirmed` 订单请求 shipments
- **THEN** 响应状态码 SHALL 为 409

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /orders/{id}/shipments`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Buyer confirms receipt

系统 SHALL 提供 `POST /orders/{id}/confirm-receipt`（需认证，仅买家）。成功时 SHALL 将 `shipped` 订单迁移为 `completed`，响应 **200**。

#### Scenario: 确认收货成功

- **WHEN** 买家对本人的 `shipped` 订单请求 confirm-receipt
- **THEN** 响应状态码 SHALL 为 200
- **AND** 订单 `status` SHALL 为 `completed`

#### Scenario: 非 shipped 确认收货返回 409

- **WHEN** 买家对非 `shipped` 订单请求 confirm-receipt
- **THEN** 响应状态码 SHALL 为 409

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /orders/{id}/confirm-receipt`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Cancel by buyer or seller with stock release

系统 SHALL 提供 `POST /orders/{id}/cancel`。买家（订单所有者）或本店店主 SHALL 可在 `awaiting_payment`、`confirmed`、`shipped` 取消订单；成功时 `status=cancelled`，`cancel_reason` 分别为 `buyer_cancelled` 或 `seller_cancelled`，并释放库存（条件更新成功时）。`completed` 与已 `cancelled` SHALL 返回 **409** 且不释放库存。

#### Scenario: 买家取消待支付订单并释放库存

- **WHEN** 买家对 `awaiting_payment` 订单请求 cancel
- **THEN** 响应状态码 SHALL 为 200
- **AND** `status` SHALL 为 `cancelled` 且 `cancel_reason` 为 `buyer_cancelled`
- **AND** 库存 SHALL 加回各行 qty

#### Scenario: 卖家取消已确认订单

- **WHEN** 本店店主对 `confirmed` 订单请求 cancel
- **THEN** 响应状态码 SHALL 为 200
- **AND** `cancel_reason` SHALL 为 `seller_cancelled`
- **AND** 库存 SHALL 加回

#### Scenario: completed 禁止取消

- **WHEN** 买家或卖家对 `completed` 订单请求 cancel
- **THEN** 响应状态码 SHALL 为 409
- **AND** 库存 SHALL NOT 变化

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /orders/{id}/cancel`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: List and get orders

系统 SHALL 提供 `GET /orders`（买家本人分页列表）、`GET /orders/{id}`（买家本人或本店店主；否则 **404**）、`GET /shops/me/orders`（店主本店分页列表）。`GET /orders/{id}`、`GET /orders` 与 `GET /shops/me/orders` SHALL 对涉及的 `awaiting_payment` 订单触发懒释放检查。分页参数 SHALL 与 catalog 列表惯例一致（`limit`/`offset`）。

#### Scenario: 买家列表仅含自己的订单

- **WHEN** 买家请求 `GET /orders`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 返回项的 `buyer_user_id` SHALL 均为当前用户

#### Scenario: 买家列表可见买家发起的订单

- **WHEN** 买家通过 `POST /orders` 建单后请求 `GET /orders`
- **THEN** 响应 SHALL 包含该订单且 `initiated_by` 为 `buyer`

#### Scenario: 店主列表可见买家发起的订单

- **WHEN** 买家在某店建单后，该店店主请求 `GET /shops/me/orders`
- **THEN** 响应 SHALL 包含该订单

#### Scenario: 无关用户获取订单返回 404

- **WHEN** 既非买家也非本店店主的用户请求 `GET /orders/{id}`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 店主列表本店订单

- **WHEN** 店主请求 `GET /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 返回项的 `shop_id` SHALL 均为该店主店铺 id

#### Scenario: 未认证列表或详情返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `GET /orders`、`GET /orders/{id}` 或 `GET /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Cross-domain boundary for catalog

ordering 域 SHALL 仅通过 `catalog.service` 与 catalog schemas 访问商品与库存；SHALL NOT import `app.catalog.models` 或 `app.catalog.repository`。

#### Scenario: ordering 包无 catalog 持久化 import

- **WHEN** 静态检查 `app/ordering/` 源码 import
- **THEN** SHALL NOT 出现对 `app.catalog.models` 或 `app.catalog.repository` 的引用
