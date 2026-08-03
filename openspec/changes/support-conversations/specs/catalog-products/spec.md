# catalog-products

## ADDED Requirements

### Requirement: Shop support context service method

catalog 域 SHALL 通过 **service**（非 repository 对外、**无 HTTP 路由**）提供 `get_shop_for_support(shop_id) -> ShopSupportContext`，供 support 域会话创建与校验使用。`ShopSupportContext` SHALL 至少包含：`id`、`status`（`active` \| `closed`）、`owner_user_id`。shop 不存在时 service SHALL 抛出 **404** HTTPException。support SHALL NOT import catalog ORM。

#### Scenario: 返回 shop 支持上下文

- **WHEN** support 调用 `get_shop_for_support` 且 shop 存在
- **THEN** SHALL 返回 `ShopSupportContext`，字段与数据库一致

#### Scenario: shop 不存在抛 404

- **WHEN** support 调用 `get_shop_for_support` 且 shop 不存在
- **THEN** SHALL 抛出 HTTP 404 异常

### Requirement: Product refs validation for support

catalog 域 SHALL 通过 **service** 提供 `validate_product_refs_for_shop(shop_id, product_ids) -> None`，供 support 域校验消息中的 product 引用。任一 `product_id` 不存在或 `product.shop_id != shop_id` 时 SHALL 抛出 **422** HTTPException。SHALL **不按**公开可见性过滤：未上架商品若属于该 shop SHALL 视为合法。support SHALL NOT import catalog ORM。

#### Scenario: 全部 product 属于 shop 时成功

- **WHEN** support 调用 `validate_product_refs_for_shop` 且所有 id 存在且 `shop_id` 匹配
- **THEN** SHALL 正常返回（不抛异常）

#### Scenario: 不存在 product 抛 422

- **WHEN** 任一 `product_id` 在 catalog 不存在
- **THEN** SHALL 抛出 HTTP 422 异常

#### Scenario: 跨 shop product 抛 422

- **WHEN** product 存在但 `shop_id` 与参数不一致
- **THEN** SHALL 抛出 HTTP 422 异常

#### Scenario: 未上架本店 product 允许

- **WHEN** product 属于该 shop 且 `is_published=false`
- **THEN** SHALL 正常返回
