## ADDED Requirements

### Requirement: Seller creates order for specified buyer

系统 SHALL 提供 `POST /shops/me/orders`（需认证，仅已开店店主）。请求体 SHALL 为 `{ "buyer_user_id": "<uuid>", "items": [ { "product_id", "qty" }, ... ] }`，至少一行；`qty` SHALL **≥ 1**。成功时 SHALL 创建 `status=awaiting_payment`、`initiated_by=seller` 的订单，设置 `expires_at`，计算 `total_amount` 与行快照，并通过 **catalog.service** 预留库存；响应 **201**。所有商品 SHALL 属于**卖家自己的店铺**（`product.shop_id == 当前店主店铺 id`）；库存/可购规则 SHALL 与买家建单相同。

#### Scenario: 卖家建单成功

- **WHEN** 店主对本店 active 下已上架且库存充足的商品，为另一有效用户提交合法 `POST /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 `status` SHALL 为 `awaiting_payment`
- **AND** 响应体 `initiated_by` SHALL 为 `seller`
- **AND** 响应体 `buyer_user_id` SHALL 为请求中的 `buyer_user_id`
- **AND** 对应商品可售库存 SHALL 已按 qty 减少

#### Scenario: 指定买家不存在返回 404

- **WHEN** 店主提交的 `buyer_user_id` 在 users 表中不存在
- **THEN** 响应状态码 SHALL 为 404
- **AND** SHALL NOT 创建订单

#### Scenario: 指定买家已禁用返回 422

- **WHEN** 店主提交的 `buyer_user_id` 对应用户 `is_active=false`
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单

#### Scenario: 卖家指定本人为买家返回 403

- **WHEN** 店主提交的 `buyer_user_id` 等于本店 `owner_user_id`
- **THEN** 响应状态码 SHALL 为 403
- **AND** SHALL NOT 创建订单

#### Scenario: 店铺 closed 返回 422

- **WHEN** 店主店铺 `status=closed` 时提交建单
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 无店铺返回 404

- **WHEN** 已认证但尚未开店的用户请求 `POST /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 非本店商品返回 422

- **WHEN** 店主提交的 `items` 中含不属于本店（`product.shop_id != 店主店铺 id`）的商品，即使所有商品同属另一单一店铺
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建订单
- **AND** 库存 SHALL NOT 被扣减

### Requirement: Seller-initiated order pay and visibility

卖家发起的 `awaiting_payment` 订单 SHALL 由指定买家通过既有 `POST /orders/{id}/pay` 支付进入 `confirmed`。指定买家 SHALL 能在 `GET /orders` 与 `GET /orders/{id}` 看到该订单。本店店主 SHALL 能在 `GET /shops/me/orders` 看到该订单。

#### Scenario: 指定买家支付卖家发起的订单

- **WHEN** 指定买家对 `initiated_by=seller` 且 `status=awaiting_payment` 的本人订单请求 pay
- **THEN** 响应状态码 SHALL 为 200
- **AND** 订单 `status` SHALL 为 `confirmed`

#### Scenario: 卖家不能支付订单

- **WHEN** 店主（非 `buyer_user_id`）对卖家发起的订单请求 pay
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 指定买家在列表中看到卖家发起的订单

- **WHEN** 卖家建单成功后，指定买家请求 `GET /orders`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 返回项 SHALL 包含该订单且 `initiated_by` 为 `seller`

#### Scenario: 店主在列表中看到卖家发起的订单

- **WHEN** 卖家建单成功后，店主请求 `GET /shops/me/orders`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 返回项 SHALL 包含该订单

### Requirement: Cross-domain boundary for user

ordering 域 SHALL 通过 `user.service.get_user_summary` 与 `UserSummary` schema 校验买家；SHALL NOT import `app.user.models` 或 `app.user.repository`。

#### Scenario: ordering 包无 user 持久化 import

- **WHEN** 静态检查 `app/ordering/` 源码 import
- **THEN** SHALL NOT 出现对 `app.user.models` 或 `app.user.repository` 的引用
