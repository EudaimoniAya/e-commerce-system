## MODIFIED Requirements

### Requirement: List and get orders

系统 SHALL 提供 `GET /orders`（买家本人分页列表）、`GET /orders/{id}`（买家本人或本店店主；否则 **404**）、`GET /shops/me/orders`（店主本店分页列表）。`GET /orders/{id}`、`GET /orders` 与 `GET /shops/me/orders` SHALL 对涉及的 `awaiting_payment` 订单触发懒释放检查。两个列表端点的分页 Query 与响应 envelope SHALL 符合 **infra-pagination** 契约（域内 alias 为 `PaginatedOrders`）。

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
