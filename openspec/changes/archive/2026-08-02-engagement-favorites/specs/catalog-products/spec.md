## ADDED Requirements

### Requirement: Batch product lookup for engagement

catalog 域 SHALL 通过 **service**（非 repository 对外、**无 HTTP 路由**）提供 `get_products_for_engagement(product_ids: list[str]) -> list[EngagementProduct]`，供 engagement 域收藏列表分类与 POST 存在性校验使用。返回类型 SHALL 为 Pydantic schema `EngagementProduct`，字段 SHALL 至少包含：`id`、`shop_id`、`shop_name`、`name`、`price`、`image_url`（可空）、`is_published`、`shop_active`（bool，表示店铺 `status=active`）。查询 SHALL **不按**公开可见性过滤：已存在但未上架或关店商品 SHALL 仍出现在返回列表中。未找到的 `product_id` SHALL NOT 出现在返回列表中。engagement SHALL NOT import catalog ORM。

`EngagementProduct` 与 `get_products_for_engagement` SHALL 与既有 `get_purchasable_products` **共用**同一 repository 层批量按 id 查询实现（单一 SQL 来源）；各 service 方法 SHALL 各自映射为不同 DTO。既有 `get_purchasable_products` 行为与返回类型 SHALL NOT 改变。

#### Scenario: service 返回 engagement 所需字段

- **WHEN** engagement 调用 `get_products_for_engagement` 传入存在的 `product_id` 列表
- **THEN** 每个找到的商品 SHALL 映射为 `EngagementProduct` 且含 id、shop_id、shop_name、name、price、image_url、is_published、shop_active
- **AND** SHALL NOT 泄漏 ORM 实例出 catalog 域

#### Scenario: 未上架商品仍被返回

- **WHEN** `product_id` 对应商品存在但 `is_published=false`
- **THEN** 该 id SHALL 出现在返回列表中
- **AND** `is_published` SHALL 为 false

#### Scenario: 不存在的 id 不在返回列表

- **WHEN** `product_ids` 含 catalog 中不存在的 id
- **THEN** 返回列表 SHALL NOT 含该 id

#### Scenario: 无新增 HTTP 路由

- **WHEN** 客户端请求任意 HTTP 路径以批量查询 engagement 商品
- **THEN** 系统 SHALL NOT 提供该 REST 端点（仅 service 层供域间调用）

#### Scenario: get_purchasable_products 行为不变

- **WHEN** ordering 调用既有 `get_purchasable_products`
- **THEN** 返回 `list[PurchasableProduct]` 语义与字段 SHALL 与本 change 前一致
