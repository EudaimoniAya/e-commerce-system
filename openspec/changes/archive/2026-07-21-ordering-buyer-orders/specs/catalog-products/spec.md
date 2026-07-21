## ADDED Requirements

### Requirement: Purchasable product lookup for ordering

catalog 域 SHALL 通过 **service**（非 repository 对外）提供批量查询可购商品信息的能力，供 ordering 域下单校验使用。返回的 schema SHALL 至少包含：`id`、`shop_id`、`name`、`price`、`stock`、店铺是否 `active`、`is_published`、以及店主用户 id（或等价字段以便 ordering 校验禁自购）。ordering SHALL NOT import catalog ORM。

#### Scenario: service 返回可购校验所需字段

- **WHEN** ordering 调用 catalog service 批量查询给定 `product_id` 列表
- **THEN** 每个找到的商品 SHALL 暴露 id、shop_id、name、price、stock、is_published、店铺 active 状态与 owner_user_id（或等价）
- **AND** 返回类型 SHALL 为 Pydantic schema（或等价 DTO），不得泄漏 ORM 实例出 catalog 域

### Requirement: Conditional stock reserve and release

catalog 域 SHALL 提供 service 方法，以 **条件更新** 扣减与加回 `products.stock`：预留时 `UPDATE ... SET stock = stock - :qty WHERE id = :id AND stock >= :qty`；任一行影响行数为 0 时 SHALL 失败且不部分提交（与调用方同一事务时整单回滚）。释放时 SHALL 将对应 qty 加回 `stock`。上述写路径 SHALL 仅通过 catalog service 暴露给 ordering。

#### Scenario: 库存充足时预留成功

- **WHEN** ordering 在同一事务中请求预留且当前 `stock >= qty`
- **THEN** 预留 SHALL 成功
- **AND** `stock` SHALL 减少 qty

#### Scenario: 库存不足时预留失败

- **WHEN** ordering 请求预留且 `stock < qty`
- **THEN** 预留 SHALL 失败
- **AND** 该商品 `stock` SHALL 保持不变（失败行未扣减；同事务内其他已扣行随回滚恢复）

#### Scenario: 释放加回库存

- **WHEN** ordering 在成功将订单条件更新为取消/过期后请求释放
- **THEN** 对应商品 `stock` SHALL 增加所释放的 qty
