## MODIFIED Requirements

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
