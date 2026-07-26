# ordering-buyer-cart

## Purpose

ordering 域买家购物车垂直切片：cart 暂存（多店、实时价展示）、按店分组列表与失效项、部分 checkout（单事务按店建单 + 轻量 checkout_batch）、通用 batch-pay；与 `POST /orders` 立即购买并行。表：`cart_items`、`checkout_batches`；`orders.checkout_batch_id`（migration `007`）。

## ADDED Requirements

### Requirement: HTTP 422 vs 409 convention (cart and batch-pay)

本 capability 业务 4xx SHALL 与 `ordering-buyer-orders` 一致：

- **422**：无法按规则创建/写入（checkout 库存不足、不可购、空/非法 cart_item_ids、重复 POST 同 product 加购等）
- **409**：对已存在订单的非法 pay/batch-pay（非 awaiting_payment、已过期、重复 pay）
- **403**：自购；**401**：未认证

#### Scenario: checkout 业务约束失败使用 422

- **WHEN** `POST /cart/checkout` 因库存不足、不可购、cart_item 不属于用户或 ids 为空而失败
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建 checkout_batch 或 orders
- **AND** 对应 cart_items SHALL 保持不变

#### Scenario: checkout 空 cart_item_ids 返回 422

- **WHEN** 认证用户 `POST /cart/checkout` 提交 `{ "cart_item_ids": [] }`
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建 checkout_batch 或 orders

#### Scenario: batch-pay 非法状态使用 409

- **WHEN** 客户端对非 `awaiting_payment` 或已过期订单请求 `POST /orders/batch-pay`
- **THEN** 响应状态码 SHALL 为 409

### Requirement: Cart items table

系统 SHALL 在 **ordering 域** 拥有 `cart_items` 表（migration `007`）。每行 SHALL 表示一用户对一商品的暂存数量；SHALL NOT 声明跨域 SQLAlchemy relationship。

#### Scenario: cart_items 表包含必需字段

- **WHEN** 查询 `cart_items` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`user_id`、`product_id`、`qty`（> 0）、`created_at`、`updated_at`
- **AND** SHALL 有 `UNIQUE(user_id, product_id)`

### Requirement: Checkout batches table and orders extension

系统 SHALL 拥有 `checkout_batches` 表（migration `007`），仅含 `id`、`buyer_user_id`、`created_at`。`orders` SHALL 新增可空列 `checkout_batch_id`（FK 语义 → `checkout_batches.id`）。通过 `POST /orders` 立即购买创建的订单 SHALL 有 `checkout_batch_id IS NULL`。

#### Scenario: checkout_batches 为轻量分组

- **WHEN** 查询 `checkout_batches` 表结构
- **THEN** SHALL NOT 含行项目、总价或 status 列

#### Scenario: 立即购买订单无 batch

- **WHEN** 买家通过 `POST /orders` 建单
- **THEN** 该订单 `checkout_batch_id` SHALL 为 NULL

### Requirement: Authenticated cart CRUD

系统 SHALL 提供购物车 API（均需 Bearer 认证）。未认证 SHALL 返回 **401**。系统 SHALL NOT 支持未登录购物车。

#### Scenario: 新增加购

- **WHEN** 认证用户 `POST /cart/items` 提交 `{ "product_id", "qty" }`（qty ≥ 1）且商品存在、该 user 尚无此行
- **THEN** 响应状态码 SHALL 为 201
- **AND** SHALL 创建 cart_item

#### Scenario: 商品不存在时加购返回 422

- **WHEN** 认证用户 `POST /cart/items` 提交的 `product_id` 在 catalog 中不存在
- **THEN** 响应状态码 SHALL 为 422（SHALL NOT 为 404）
- **AND** SHALL NOT 创建 cart_item

#### Scenario: 重复加购同一商品返回 422

- **WHEN** 认证用户对已存在于 cart 的 `product_id` 再次 `POST /cart/items`
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 累加 qty（须用 PATCH 改数量）

#### Scenario: 修改数量

- **WHEN** 认证用户 `PATCH /cart/items/{id}` 提交合法 `qty`（≥ 1）且该行属本人
- **THEN** 响应状态码 SHALL 为 200
- **AND** cart_item qty SHALL 更新

#### Scenario: 删除 cart 行

- **WHEN** 认证用户 `DELETE /cart/items/{id}` 且该行属本人
- **THEN** 响应状态码 SHALL 为 204
- **AND** 该行 SHALL 被删除

#### Scenario: 操作他人 cart 行

- **WHEN** 认证用户 PATCH/DELETE 不属于自己的 cart_item
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: cart_item id 不存在

- **WHEN** 认证用户 PATCH/DELETE 的 cart_item id 不存在
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Cart list grouped by shop with catalog enrichment

系统 SHALL 提供 `GET /cart`（需认证）。SHALL 通过 **catalog.service**（如 `get_purchasable_products`）**批量**查询商品（一次传入全部 product_id，避免 N+1）；SHALL NOT import catalog ORM。可购且已上架、店铺 active 的行 SHALL 归入 `shops[]`（按 `shop_id` 分组，含实时 `unit_price` 等展示字段）。不可购行 SHALL 归入 `invalid_items[]`（含 `reason`）。系统 SHALL NOT 在 GET 时自动删除失效行。空 cart SHALL 返回 `{ "shops": [], "invalid_items": [] }`。

#### Scenario: 空购物车响应

- **WHEN** 认证用户 cart 无任何行并请求 `GET /cart`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为 `{ "shops": [], "invalid_items": [] }`

#### Scenario: 按店分组展示有效行

- **WHEN** 认证用户 cart 含多店可购商品并请求 `GET /cart`
- **THEN** 响应 SHALL 含 `shops` 数组，每元素含 `shop_id` 与 `items`
- **AND** 每项 SHALL 含 `cart_item_id`、`product_id`、`qty` 及 catalog 实时价

#### Scenario: 失效行进入 invalid_items

- **WHEN** cart 中某 product 已下架或店铺非 active 或不存在
- **THEN** 该行 SHALL 出现在 `invalid_items` 而非 `shops`
- **AND** cart_items 表中该行 SHALL 仍存在直至用户 DELETE

### Requirement: Partial cart checkout in single transaction

系统 SHALL 提供 `POST /cart/checkout`（需认证）。请求体 SHALL 为 `{ "cart_item_ids": ["...", ...] }`（非空）。SHALL 仅处理指定行（部分结算）；未包含行 SHALL 保留在 cart。在同一 DB 事务内 SHALL：创建 `checkout_batch`；按 `shop_id` 分组；每组调用 ordering 建单逻辑创建 `status=awaiting_payment`、`initiated_by=buyer` 的子订单并设置 `checkout_batch_id`、预留库存、快照价格；删除已结算 cart_items。任一失败 SHALL 全 rollback。成功 SHALL 响应 **201** 含 `checkout_batch_id` 与 `orders` 数组。

#### Scenario: 跨店 checkout 成功

- **WHEN** 认证用户提交属于多店的合法 cart_item_ids 且均可购、库存充足、非自购
- **THEN** 响应状态码 SHALL 为 201
- **AND** SHALL 创建 1 个 checkout_batch 与 N 个 orders（每店 1 单）
- **AND** 所有子订单 `checkout_batch_id` SHALL 相同
- **AND** 已结算 cart_items SHALL 被删除
- **AND** 未提交 cart_items SHALL 仍存在

#### Scenario: checkout 失败 cart 不变

- **WHEN** checkout 因库存不足或不可购失败
- **THEN** 响应状态码 SHALL 为 422
- **AND** 所有 cart_items SHALL 保持 checkout 前状态

#### Scenario: checkout 锁价快照

- **WHEN** checkout 成功创建 orders
- **THEN** 各 `order_items.unit_price` SHALL 为 checkout 时刻 catalog 价格快照
- **AND** 后续 catalog 调价 SHALL NOT 改变这些 order_items

#### Scenario: 店主自购 checkout 返回 403

- **WHEN** checkout 含本店商品且买家为店主
- **THEN** 响应状态码 SHALL 为 403
- **AND** SHALL NOT 创建 batch 或 orders

### Requirement: Checkout batch detail for grouped display

系统 SHALL 提供 `GET /checkout-batches/{id}`（需认证，仅 `buyer_user_id` 本人）。SHALL 返回该 batch 下子 orders 的层级结构及聚合字段（如 `paid_total`、`remaining_total`、派生展示 status）。SHALL 在读路径触发子订单懒释放（`expire_if_needed`）。父级 SHALL NOT 有独立 pay 端点。

#### Scenario: 买家查看结算分组

- **WHEN** 买家请求本人的 checkout_batch
- **THEN** 响应状态码 SHALL 为 200
- **AND** SHALL 含按店分组的 orders 及 items
- **AND** `remaining_total` SHALL 为仍 `awaiting_payment` 子单的 total_amount 之和

#### Scenario: 非本人查看 batch 返回 404

- **WHEN** 其他用户请求该 checkout_batch
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: batch 含已取消子单时 remaining_total 正确

- **WHEN** checkout_batch 下部分子单为 `confirmed`、部分为 `cancelled`（含过期）、部分仍为 `awaiting_payment`
- **THEN** `GET /checkout-batches/{id}` 响应 SHALL 逐单展示真实 status
- **AND** `remaining_total` SHALL 仅含仍 `awaiting_payment` 子单的 total_amount 之和

### Requirement: General batch payment stub

系统 SHALL 提供 `POST /orders/batch-pay`（需认证）。请求体 SHALL 为 `{ "order_ids": ["...", ...] }`（非空）。SHALL 将所列订单从 `awaiting_payment` 迁移为 `confirmed`（支付桩，永远成功）。全部 order_ids SHALL 属当前买家、均为 `awaiting_payment` 且未过期；**不要求**同一 `checkout_batch_id`；**不要求**付清某 batch 全部子单。SHALL **先**对全部 id 执行 `expire_if_needed`，**再**校验；任一不满足 SHALL 返回 **409** 或 **404**/**403**（与单笔 pay 一致），且 **SHALL NOT** 部分确认（全有或全无，单事务）。SHALL NOT 再次扣减库存。

#### Scenario: batch-pay 空 order_ids 返回 422

- **WHEN** 认证用户 `POST /orders/batch-pay` 提交 `{ "order_ids": [] }`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: batch-pay 多订单成功

- **WHEN** 买家对多个本人的未过期 awaiting_payment 订单提交 batch-pay
- **THEN** 响应状态码 SHALL 为 200
- **AND** 所列订单 status SHALL 均为 `confirmed`

#### Scenario: batch-pay 可跨 batch 与立即购买单

- **WHEN** order_ids 含不同 checkout_batch_id 的订单及 checkout_batch_id 为 NULL 的立即购买订单，且均可 pay
- **THEN** batch-pay SHALL 成功

#### Scenario: batch-pay 部分非法则全部失败

- **WHEN** order_ids 中任一订单非 awaiting_payment 或已过期或非本人
- **THEN** 响应状态码 SHALL 为 409 或 403/404
- **AND** 所有订单 status SHALL 保持 batch-pay 前状态

#### Scenario: batch-pay 部分过期则零确认

- **WHEN** order_ids 中部分订单已过期（经 `expire_if_needed` 后为 cancelled）、部分仍 awaiting_payment
- **THEN** 响应状态码 SHALL 为 409
- **AND** 所有订单（含原本可 pay 的单）status SHALL 保持 batch-pay 前状态

#### Scenario: batch-pay 子集支付

- **WHEN** 某 checkout_batch 有 3 个子单 awaiting_payment，买家 batch-pay 其中 2 个
- **THEN** 响应状态码 SHALL 为 200
- **AND** 仅该 2 单 SHALL 变为 `confirmed`
- **AND** 第 3 单 SHALL 仍为 `awaiting_payment`

### Requirement: Immediate buy path unchanged

系统 SHALL 保留 `POST /orders` 与 `POST /orders/{id}/pay` 行为与 `ordering-buyer-orders` 一致。购物车路径 SHALL NOT 替代立即购买。

#### Scenario: 立即购买不经过 cart

- **WHEN** 买家 `POST /orders` 合法同店 items
- **THEN** SHALL 201 创建单订单且无 checkout_batch_id
- **AND** 行为 SHALL 与 ordering-buyer-orders 一致

### Requirement: Cross-domain boundaries

cart 与 checkout 实现 SHALL 仅通过 **catalog.service** 与 **catalog.schemas** 访问商品/库存；ordering SHALL NOT import `catalog.models` 或 `catalog.repository`。

#### Scenario: 禁止跨域 ORM import

- **WHEN** 审查 `app/ordering/` 下 cart/checkout 相关模块
- **THEN** SHALL NOT 存在 `from catalog.models import` 或 `from catalog.repository import`
