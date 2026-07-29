# catalog-shop

## Purpose

catalog 域店铺垂直切片：开店、店主查询/更新、`GET /shops/{shop_id}` 公开详情与 `shops` 表；为后续 catalog-products（类目、商品）与 ordering 提供店铺实体。

## Requirements

### Requirement: Shop creation for authenticated users

系统 SHALL 提供 `POST /shops`，接受 JSON 请求体（`name` 必填；`description`、`logo_url` 可选）；已认证用户 SHALL 可创建店铺；创建成功返回 201 与店铺资料。

#### Scenario: 开店成功

- **WHEN** 已认证用户提交有效且唯一的 `name`，且该用户尚无店铺
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 JSON SHALL 包含 `id`、`owner_user_id`（与 JWT sub 一致）、`name`、`description`、`logo_url`、`status`（值为 `active`）、`created_at`、`updated_at`

#### Scenario: 用户已有店铺返回 422

- **WHEN** 已认证用户已拥有店铺（`shops.owner_user_id` 已存在）再次请求 `POST /shops`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 店名已存在返回 422

- **WHEN** 已认证用户提交的 `name` 已被其他店铺使用
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /shops`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Current user's shop endpoint

系统 SHALL 提供需认证的 `GET /shops/me`，返回当前用户作为 owner 的店铺。

#### Scenario: 有店铺返回 200

- **WHEN** 已认证用户已拥有店铺
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 为完整店铺对象（字段同开店成功响应）

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户尚未创建店铺
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `GET /shops/me`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Shop update for owner

系统 SHALL 提供需认证的 `PATCH /shops/me`，允许店主更新 `name`、`description`、`logo_url`、`status`（`active` 或 `closed`）。

#### Scenario: 更新成功返回 200

- **WHEN** 已认证店主提交合法字段（如修改 `name` 或设置 `status` 为 `closed`）
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 反映更新后的店铺资料

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户尚无店铺请求 `PATCH /shops/me`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 店名冲突返回 422

- **WHEN** 店主提交的 `name` 与其他店铺重复
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `PATCH /shops/me`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Public shop detail

系统 SHALL 提供公开的 `GET /shops/{shop_id}`，无需认证。

#### Scenario: 活跃店铺返回 200

- **WHEN** 客户端请求存在的店铺且 `status` 为 `active`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 包含完整店铺字段含 `status: active`

#### Scenario: 已关闭店铺仍返回 200

- **WHEN** 客户端请求存在的店铺且 `status` 为 `closed`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 包含 `status: closed`（供前端展示关店状态）

#### Scenario: 店铺不存在返回 404

- **WHEN** 客户端请求的 `shop_id` 不存在
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Shops table with owner uniqueness

系统 SHALL 在 **catalog 域** 拥有 `shops` 表；`owner_user_id` SHALL 外键引用 `users.id` 且 **UNIQUE**（当前一用户一店）。

#### Scenario: 店铺记录包含必需字段

- **WHEN** 查询 `shops` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`owner_user_id`（FK UNIQUE）、`name`（UNIQUE）、`description`（可空）、`logo_url`（可空）、`status`、`created_at`、`updated_at`

### Requirement: Catalog shop domain layered structure

catalog 域（本 change 至少 shop 子模块）SHALL 采用 router → service → repository → model + schemas 分层；跨域 SHALL 仅使用 `infra.auth.get_current_user_id` 或未来 catalog 公开 service/schema，SHALL NOT 由其他域 import `app.catalog.models` 或 `app.catalog.repository`。

#### Scenario: 店铺路由由应用挂载

- **WHEN** 测试客户端请求 `POST /shops` 或 `GET /shops/me` 或 `GET /shops/{shop_id}`
- **THEN** 请求 SHALL 由 FastAPI 应用处理（非 404）

### Requirement: Multi-shop extensibility documented

本 change SHALL 通过 `owner_user_id` UNIQUE 实现 1:1；设计文档 SHALL 记录未来多店铺可通过移除 UNIQUE 并引入 `shop_members` 扩展，本 change 不要求实现多店铺。

#### Scenario: 当前约束为一对一

- **WHEN** 同一 `owner_user_id` 尝试插入第二条 shop 记录
- **THEN** 数据库或业务层 SHALL 拒绝（UNIQUE 或 422）
