# catalog-shop (delta)

## MODIFIED Requirements

### Requirement: Shop creation for authenticated users

系统 SHALL 提供 `POST /shops`，接受 JSON 请求体（`name` 必填；`description`、`logo_media_id` 可选）；已认证用户 SHALL 可创建店铺；若提供 `logo_media_id` SHALL 经 media attach 校验并 `mark_public`；创建成功返回 201 与店铺资料（含 resolve 后的 `logo_url`）。

#### Scenario: 开店成功

- **WHEN** 已认证用户提交有效且唯一的 `name`，且该用户尚无店铺
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 JSON SHALL 包含 `id`、`owner_user_id`（与 JWT sub 一致）、`name`、`description`、`logo_url`（可 null）、`status`（值为 `active`）、`created_at`、`updated_at`

#### Scenario: 用户已有店铺返回 422

- **WHEN** 已认证用户已拥有店铺（`shops.owner_user_id` 已存在）再次请求 `POST /shops`
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 店名已存在返回 422

- **WHEN** 已认证用户提交的 `name` 已被其他店铺使用
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `POST /shops`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Shop update for owner

系统 SHALL 提供需认证的 `PATCH /shops/me`，允许店主更新 `name`、`description`、`logo_media_id`（可 null 清空）、`status`（`active` 或 `closed`）。设置 `logo_media_id` 时 SHALL 经 media attach 校验（owner + `image/*`）。

#### Scenario: 更新成功返回 200

- **WHEN** 已认证店主提交合法字段（如修改 `name` 或设置 `status` 为 `closed`）
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 反映更新后的店铺资料（含 `logo_url`）

#### Scenario: 无店铺返回 404

- **WHEN** 已认证用户尚无店铺请求 `PATCH /shops/me`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 店名冲突返回 422

- **WHEN** 店主提交的 `name` 与其他店铺重复
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求 `PATCH /shops/me`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 绑他人 logo media 返回 403

- **WHEN** 店主 PATCH 非本人 owner 的 `logo_media_id`
- **THEN** 响应状态码 SHALL 为 403

### Requirement: Shops table with owner uniqueness

系统 SHALL 在 **catalog 域** 拥有 `shops` 表；`owner_user_id` SHALL 外键引用 `users.id` 且 **UNIQUE**（当前一用户一店）。

#### Scenario: 店铺记录包含必需字段

- **WHEN** 查询 `shops` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`owner_user_id`（FK UNIQUE）、`name`（UNIQUE）、`description`（可空）、`logo_media_id`（可空 FK → `media_assets.id`）、`status`、`created_at`、`updated_at`
- **AND** SHALL NOT 含 `logo_url` 列
