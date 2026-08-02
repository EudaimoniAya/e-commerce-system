# engagement-favorites

## Purpose

engagement 域用户商品收藏垂直切片：认证用户收藏/取消/分页列表（可展示项与失效项分类）、批量 batch-delete（前端提交 product_ids）。表：`user_favorites`（migration `009`）。跨域读路径调用 `catalog.service.get_products_for_engagement` → `EngagementProduct`；禁止 import catalog ORM/repository。

## ADDED Requirements

### Requirement: user_favorites table

系统 SHALL 在 **engagement 域** 拥有 `user_favorites` 表（migration `009`）。每行 SHALL 表示一用户对一商品的收藏；SHALL NOT 声明跨域 SQLAlchemy relationship。

#### Scenario: user_favorites 表包含必需字段

- **WHEN** 查询 `user_favorites` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`user_id`、`product_id`、`created_at`
- **AND** SHALL 有 `UNIQUE(user_id, product_id)`

### Requirement: Authenticated favorites API

系统 SHALL 提供收藏 API（均需 Bearer 认证）。未认证 SHALL 返回 **401**。URL SHALL NOT 包含 `{user_id}`；当前用户 SHALL 由 JWT `sub` 解析。

#### Scenario: 未认证 POST 返回 401

- **WHEN** 未认证客户端 `POST /favorites`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 未认证 GET 返回 401

- **WHEN** 未认证客户端 `GET /favorites`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: POST /favorites

系统 SHALL 提供 `POST /favorites`，body `{ "product_id": "<uuid>" }`。

#### Scenario: 首次收藏成功

- **WHEN** 认证用户 POST 且 `product_id` 在 catalog 存在、该用户尚无此收藏
- **THEN** 响应状态码 SHALL 为 201
- **AND** SHALL 创建 `user_favorites` 行

#### Scenario: 重复收藏幂等

- **WHEN** 认证用户对已收藏的 `product_id` 再次 POST
- **THEN** 响应状态码 SHALL 为 200
- **AND** SHALL NOT 创建重复行
- **AND** SHALL 返回既有 favorite 信息

#### Scenario: 商品不存在返回 422

- **WHEN** 认证用户 POST 的 `product_id` 在 catalog 中不存在
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 创建 favorite

#### Scenario: 未上架商品允许收藏

- **WHEN** 认证用户 POST 的 `product_id` 对应商品存在但 `is_published=false`
- **THEN** 响应状态码 SHALL 为 201 或 200（幂等）
- **AND** SHALL 创建或返回 favorite 行

### Requirement: DELETE /favorites/{product_id}

系统 SHALL 提供 `DELETE /favorites/{product_id}`，按商品 ID 取消收藏。

#### Scenario: 取消已收藏商品

- **WHEN** 认证用户 DELETE 其已收藏的 `product_id`
- **THEN** 响应状态码 SHALL 为 204
- **AND** 对应 favorite 行 SHALL 被删除

#### Scenario: 取消未收藏商品返回 404

- **WHEN** 认证用户 DELETE 其未收藏的 `product_id`
- **THEN** 响应状态码 SHALL 为 404

### Requirement: GET /favorites paginated list

系统 SHALL 提供 `GET /favorites`，分页 Query SHALL 符合 **infra-pagination** 契约（`limit` 默认 20、最大 100；`offset` 默认 0）。响应 SHALL 包含 `items`、`unavailable_items`、`total`、`limit`、`offset`。列表 SHALL 按 favorite `created_at` 降序。`total` SHALL 为该用户 **全部** favorite 行数（含 unavailable）。

#### Scenario: 空收藏列表

- **WHEN** 认证用户无 favorite 行并 GET /favorites
- **THEN** 响应 SHALL 为 `{ "items": [], "unavailable_items": [], "total": 0, "limit": 20, "offset": 0 }`（limit/offset 随 Query）

#### Scenario: 可展示收藏在 items

- **WHEN** favorite 对应商品存在、已上架且店铺 active
- **THEN** 该 favorite SHALL 出现在 `items`
- **AND** item SHALL 含 `id`、`product_id`、`created_at`
- **AND** item SHALL NOT 含嵌套 product 价图详情（展示由前端调公开 catalog API）

#### Scenario: 未上架商品在 unavailable_items

- **WHEN** favorite 对应商品存在但 `is_published=false`
- **THEN** 该 favorite SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `product_unpublished`
- **AND** SHALL 含 `product_name`（来自 catalog service enrichment）

#### Scenario: 店铺关闭在 unavailable_items

- **WHEN** favorite 对应商品存在但所属店铺 `status=closed`
- **THEN** 该 favorite SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `shop_closed`

#### Scenario: 商品不存在于 unavailable_items

- **WHEN** favorite 的 `product_id` 在 catalog 无对应行
- **THEN** 该 favorite SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `not_found`
- **AND** `product_name` MAY 为空

### Requirement: POST /favorites/batch-delete

系统 SHALL 提供 `POST /favorites/batch-delete`，body `{ "product_ids": ["<uuid>", ...] }`（`product_ids` SHALL 至少 1 个元素，与 `POST /orders/batch-pay` 空列表约定一致）。系统 SHALL 删除当前用户收藏中 `product_id` 落在提交列表内的行；SHALL NOT 删除未出现在列表中的 favorite。未收藏过的 `product_id` SHALL 跳过（不导致整批失败）。响应 SHALL 含 `deleted_count`（实际删除行数）。

#### Scenario: batch-delete 删除提交的 unavailable product_ids

- **WHEN** 认证用户有 2 条 unavailable 与 1 条 items favorite，POST batch-delete 提交 2 个 unavailable 的 `product_id`
- **THEN** 响应状态码 SHALL 为 200
- **AND** `deleted_count` SHALL 为 2
- **AND** 再次 GET 仅剩 1 条 items favorite

#### Scenario: 未收藏的 product_id 跳过

- **WHEN** 认证用户 POST batch-delete 提交 `{ "product_ids": [已收藏id, 未收藏id] }`
- **THEN** 响应状态码 SHALL 为 200
- **AND** `deleted_count` SHALL 为 1
- **AND** 已收藏 id 对应行 SHALL 被删除

#### Scenario: 空 product_ids 返回 422

- **WHEN** 认证用户 POST batch-delete 提交 `{ "product_ids": [] }`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: batch-delete 未认证返回 401

- **WHEN** 未认证客户端 POST batch-delete
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Favorites list SHALL NOT auto-delete unavailable rows

GET /favorites SHALL NOT 自动删除 unavailable favorite 行；用户 SHALL 通过 DELETE 单条或 POST batch-delete（前端提交 product_ids）主动清理。

#### Scenario: GET 不删除下架商品收藏

- **WHEN** 商品被下架后用户 GET /favorites
- **THEN** 对应 favorite SHALL 仍存在于 `unavailable_items`
- **AND** DB 中 favorite 行 SHALL 仍存在
