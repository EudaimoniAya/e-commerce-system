## MODIFIED Requirements

### Requirement: Merchant product list

系统 SHALL 提供 `GET /shops/me/products`，需认证且用户拥有店铺；返回本店**全部**商品（含未上架）；分页 Query 与响应 envelope SHALL 符合 **infra-pagination** 契约（`limit` 默认 20、最大 100；`offset` 默认 0；响应 `Paginated[ProductResponse]`，域内 alias 为 `PaginatedProducts`）。

#### Scenario: 返回本店商品列表

- **WHEN** 店主请求 `GET /shops/me/products`
- **THEN** 响应状态码 SHALL 为 200
- **AND** `items` 中每项 SHALL 为 `ProductResponse`（含 `categories`）

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户无店铺
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Public product list and detail

系统 SHALL 提供公开 `GET /products` 与 `GET /products/{id}`；仅展示 `is_published=true` 且所属店铺 `status=active` 的商品；`GET /products` SHALL 支持可选 `category_id` 筛选；分页 Query 与响应 envelope SHALL 符合 **infra-pagination** 契约。

#### Scenario: 公开列表仅上架且店铺 active

- **WHEN** 客户端请求 `GET /products`
- **THEN** 响应状态码 SHALL 为 200
- **AND** `items` SHALL 仅含已上架且店铺 active 的商品

#### Scenario: 按 category_id 筛选

- **WHEN** 客户端请求 `GET /products?category_id={id}`
- **THEN** 响应 SHALL 仅含关联该 category 的符合条件的商品

#### Scenario: 公开详情已上架返回 200

- **WHEN** 商品已上架且店铺 active
- **THEN** `GET /products/{id}` 响应状态码 SHALL 为 200

#### Scenario: 未上架或 closed 店返回 404

- **WHEN** 商品未上架或所属店铺为 `closed`
- **THEN** `GET /products/{id}` 响应状态码 SHALL 为 404
