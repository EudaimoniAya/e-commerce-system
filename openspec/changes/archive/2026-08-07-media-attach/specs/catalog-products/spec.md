# catalog-products (delta)

## MODIFIED Requirements

### Requirement: Products table with shop ownership

系统 SHALL 拥有 `products` 表与 `product_categories` 关联表；商品 SHALL 通过 `shop_id` FK 归属店铺；类目与商品 SHALL 为多对多，关联表 SHALL 含 `is_primary`（每 product 至多一个 true）。

#### Scenario: 商品与关联表字段

- **WHEN** 查询表结构或 ORM
- **THEN** `products` SHALL 含：`id`、`shop_id`（FK）、`name`、`description`（可空）、`price`（DECIMAL(10,2)）、`stock`、`is_published`、`primary_media_id`（可空 FK → `media_assets.id`）、`created_at`、`updated_at`
- **AND** SHALL NOT 含 `image_url` 列
- **AND** `product_categories` SHALL 含：`product_id`、`category_id`、`is_primary`

### Requirement: Merchant product creation

系统 SHALL 提供 `POST /products`，需认证且当前用户拥有 **active** 店铺；请求体 **不得** 含 `shop_id`；可选 `primary_media_id`（attach 校验同 shop logo）；`service` 从店主 shop 推断 `shop_id`；创建时 `stock` SHALL **> 0**，`price` SHALL **> 0**；`category_ids` 至少 1 个，`primary_category_id` 必填且 SHALL 属于 `category_ids`。响应 `ProductResponse.image_url` SHALL 由 `primary_media_id` resolve。

#### Scenario: 创建成功返回 201

- **WHEN** 店主在 active 店铺下提交合法 body（含至少一个有效类目）
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 `ProductResponse` SHALL 含 `shop_id`、`categories`（含 `is_primary`）与 `image_url`（可 null）

#### Scenario: 店铺 closed 返回 422

- **WHEN** 店主店铺 `status` 为 `closed` 请求 `POST /products`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户无店铺请求 `POST /products`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 类目不足或 primary 无效返回 422

- **WHEN** `category_ids` 为空或 `primary_category_id` 不在 `category_ids` 中
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未认证返回 401

- **WHEN** 未携带有效 token 请求 `POST /products`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 绑他人主图 media 返回 403

- **WHEN** 店主 POST 非本人 owner 的 `primary_media_id`
- **THEN** 响应状态码 SHALL 为 403

### Requirement: Merchant product update

系统 SHALL 提供 `PATCH /products/{product_id}`，仅允许商品所属店铺的 owner 更新；非本店商品 SHALL 返回 **403**；店铺 `closed` 时 SHALL 返回 **422**；允许 `stock` 更新为 **0**；`price` 若提供 SHALL **> 0**；可提供 `category_ids` + `primary_category_id` 全量替换关联；可提供 `primary_media_id`（可 null 清空）并经 attach 校验。

#### Scenario: 本店更新成功

- **WHEN** 店主 PATCH 本店商品合法字段（如 `is_published=true`）
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为更新后的 `ProductResponse`（含 resolve 后 `image_url`）

#### Scenario: 非本店商品返回 403

- **WHEN** 店主 PATCH 其他店铺的商品
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 店铺 closed 返回 422

- **WHEN** 店主店铺为 `closed` 时 PATCH 本店商品
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 清空主图成功

- **WHEN** 店主 PATCH 本店商品 `primary_media_id` 为 null
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 `image_url` SHALL 为 null

### Requirement: Batch product lookup for engagement

catalog 域 SHALL 通过 **service**（非 repository 对外、**无 HTTP 路由**）提供 `get_products_for_engagement(product_ids: list[str]) -> list[EngagementProduct]`，供 engagement 域收藏列表分类与 POST 存在性校验使用。返回类型 SHALL 为 Pydantic schema `EngagementProduct`，字段 SHALL 至少包含：`id`、`shop_id`、`shop_name`、`name`、`price`、`image_url`（可空）、`is_published`、`shop_active`（bool，表示店铺 `status=active`）。`image_url` SHALL 由 `products.primary_media_id` 经 `media.service.resolve_urls` 填充，**不**读已删除的 URL 列。查询 SHALL **不按**公开可见性过滤：已存在但未上架或关店商品 SHALL 仍出现在返回列表中。未找到的 `product_id` SHALL NOT 出现在返回列表中。engagement SHALL NOT import catalog ORM。

`EngagementProduct` 与 `get_products_for_engagement` SHALL 与既有 `get_purchasable_products` **共用**同一 repository 层批量按 id 查询实现（单一 SQL 来源）；各 service 方法 SHALL 各自映射为不同 DTO。既有 `get_purchasable_products` 行为与返回类型 SHALL NOT 改变。

#### Scenario: service 返回 engagement 所需字段

- **WHEN** engagement 调用 `get_products_for_engagement` 传入存在的 `product_id` 列表
- **THEN** 每个找到的商品 SHALL 映射为 `EngagementProduct` 且含 id、shop_id、shop_name、name、price、image_url、is_published、shop_active
- **AND** SHALL NOT 泄漏 ORM 实例出 catalog 域

#### Scenario: 未上架商品仍被返回

- **WHEN** `product_id` 对应商品存在但 `is_published=false`
- **THEN** 该 id SHALL 出现在返回列表中
- **AND** `is_published` SHALL 为 false

#### Scenario: 有主图时 image_url 为 resolve 路径

- **WHEN** 商品存在且 `primary_media_id` 指向有效 media
- **THEN** `EngagementProduct.image_url` SHALL 为 `/media/{id}/file`

## ADDED Requirements

### Requirement: Product list paths batch resolve image_url

返回多条 `ProductResponse` 的读路径（`GET /products`、`GET /shops/me/products`）SHALL 收集页内全部非 null `primary_media_id`，**单次**调用 `media.service.resolve_urls` 批量填充 `image_url`（禁止逐条 N+1）。

#### Scenario: 公开列表批量 resolve image_url

- **WHEN** 客户端 GET `/products` 且结果含多条带 `primary_media_id` 的商品
- **THEN** 每条 `ProductResponse.image_url` SHALL 为对应 `/media/{id}/file`
- **AND** catalog service SHALL 对页内 id **单次** batch 调用 `resolve_urls`
