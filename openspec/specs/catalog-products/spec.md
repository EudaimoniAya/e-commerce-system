# catalog-products

## Purpose

catalog 域类目与商品垂直切片：平台统一类目树（admin 创建）、商品 CRUD/上下架、店主分页查询与公开浏览；`categories`、`products`、`product_categories` 三表（migration `004`，无类目 seed）。

## Requirements

### Requirement: Platform category tree

系统 SHALL 在 **catalog 域** 拥有 `categories` 表，以 `parent_id` 自引用 FK 形成不限深度的平台统一类目树；本 change **不** migration seed 初始类目。

#### Scenario: 类目表包含必需字段

- **WHEN** 查询 `categories` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`parent_id`（FK → categories.id，可空）、`name`、`created_at`、`updated_at`

### Requirement: Public category list

系统 SHALL 提供 `GET /categories`，无需认证，返回**扁平**类目列表。

#### Scenario: 返回扁平列表

- **WHEN** 客户端请求 `GET /categories`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为 JSON 数组，每项含 `id`、`parent_id`（可 null）、`name`、`created_at`、`updated_at`

#### Scenario: 空库返回空数组

- **WHEN** 尚无类目记录
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为 `[]`

### Requirement: Admin category creation

系统 SHALL 提供 `POST /categories`，需 `require_admin`；接受 JSON `{ "name", "parent_id"? }`；成功返回 201。

#### Scenario: 创建根类目成功

- **WHEN** 管理员提交有效 `name` 且未提供 `parent_id`（或 null）
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 SHALL 含新类目 `id`、`parent_id`（null）、`name`

#### Scenario: 创建子类目成功

- **WHEN** 管理员提交有效 `name` 与存在的 `parent_id`
- **THEN** 响应状态码 SHALL 为 201

#### Scenario: 同级类目名重复返回 422

- **WHEN** 管理员在同一 `parent_id` 下创建已存在的 `name`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 非管理员返回 403

- **WHEN** 非 admin 用户请求 `POST /categories`
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /categories`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Products table with shop ownership

系统 SHALL 拥有 `products` 表与 `product_categories` 关联表；商品 SHALL 通过 `shop_id` FK 归属店铺；类目与商品 SHALL 为多对多，关联表 SHALL 含 `is_primary`（每 product 至多一个 true）。

#### Scenario: 商品与关联表字段

- **WHEN** 查询表结构或 ORM
- **THEN** `products` SHALL 含：`id`、`shop_id`（FK）、`name`、`description`（可空）、`price`（DECIMAL(10,2)）、`stock`、`is_published`、`image_url`（可空）、`created_at`、`updated_at`
- **AND** `product_categories` SHALL 含：`product_id`、`category_id`、`is_primary`

### Requirement: Merchant product creation

系统 SHALL 提供 `POST /products`，需认证且当前用户拥有 **active** 店铺；请求体 **不得** 含 `shop_id`；`service` 从店主 shop 推断 `shop_id`；创建时 `stock` SHALL **> 0**，`price` SHALL **> 0**；`category_ids` 至少 1 个，`primary_category_id` 必填且 SHALL 属于 `category_ids`。

#### Scenario: 创建成功返回 201

- **WHEN** 店主在 active 店铺下提交合法 body（含至少一个有效类目）
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 `ProductResponse` SHALL 含 `shop_id` 与 `categories`（含 `is_primary`）

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

### Requirement: Merchant product update

系统 SHALL 提供 `PATCH /products/{product_id}`，仅允许商品所属店铺的 owner 更新；非本店商品 SHALL 返回 **403**；店铺 `closed` 时 SHALL 返回 **422**；允许 `stock` 更新为 **0**；`price` 若提供 SHALL **> 0**；可提供 `category_ids` + `primary_category_id` 全量替换关联。

#### Scenario: 本店更新成功

- **WHEN** 店主 PATCH 本店商品合法字段（如 `is_published=true`）
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为更新后的 `ProductResponse`

#### Scenario: 非本店商品返回 403

- **WHEN** 店主 PATCH 其他店铺的商品
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 店铺 closed 返回 422

- **WHEN** 店主店铺为 `closed` 时 PATCH 本店商品
- **THEN** 响应状态码 SHALL 为 422

### Requirement: Merchant product list

系统 SHALL 提供 `GET /shops/me/products`，需认证且用户拥有店铺；返回本店**全部**商品（含未上架）；支持 `limit`（默认 20，最大 100）与 `offset`（默认 0）；响应 `{ items, total, limit, offset }`。

#### Scenario: 返回本店商品列表

- **WHEN** 店主请求 `GET /shops/me/products`
- **THEN** 响应状态码 SHALL 为 200
- **AND** `items` 中每项 SHALL 为 `ProductResponse`（含 `categories`）

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户无店铺
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Public product list and detail

系统 SHALL 提供公开 `GET /products` 与 `GET /products/{id}`；仅展示 `is_published=true` 且所属店铺 `status=active` 的商品；`GET /products` SHALL 支持可选 `category_id` 筛选及 `limit`/`offset` 分页。

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

### Requirement: Product delisting without delete

系统 SHALL **不** 提供 `DELETE /products`；商家 SHALL 通过 `PATCH` 设置 `is_published=false` 下架。

#### Scenario: 无 DELETE 路由

- **WHEN** 客户端请求 `DELETE /products/{id}`
- **THEN** 响应状态码 SHALL 为 405 或 404（路由未实现）

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

### Requirement: Catalog products routes mounted

系统 SHALL 在 `app/main.py` 挂载类目与商品路由（可与现有 shop 路由同 catalog router）。

#### Scenario: 应用处理 products 请求

- **WHEN** 测试客户端请求 `GET /products` 或 `POST /products` 或 `GET /categories`
- **THEN** 请求 SHALL 由 FastAPI 应用处理（非 404）
