# user-auth (delta)

## MODIFIED Requirements

### Requirement: User profile update endpoint

系统 SHALL 提供需认证的 `PATCH /users/me`，允许更新可选资料字段 `email`（`EmailStr`，可 null 清空）、`nickname` 与 `avatar_media_id`（可 null 清空头像引用）；SHALL NOT 通过本端点修改 `phone` 或 `password`。设置 `avatar_media_id` 时 SHALL 调用 `media.service` 校验：`media.owner == 当前用户`（否则 403）；`content_type` 须为 `image/*`（否则 422，响应 SHALL 含 `media_id`）；成功后 SHALL 同事务 `mark_public` 并持久化 FK。

#### Scenario: 更新 email 与 nickname 成功

- **WHEN** 认证用户提交合法 `email` 和/或 `nickname`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 反映更新后的用户资料

#### Scenario: email 已被其他用户占用返回 422

- **WHEN** 客户端提交的 `email` 已被其他用户占用
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: attach 头像成功

- **WHEN** 认证用户 PATCH 合法 `avatar_media_id`（本人 upload 的 image）
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 `avatar_url` SHALL 为 `/media/{id}/file`
- **AND** 匿名 GET 该 `/media/{id}/file` SHALL 200

#### Scenario: 绑他人 media 返回 403

- **WHEN** 用户 PATCH 非本人 owner 的 `avatar_media_id`
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 非 image attach 返回 422

- **WHEN** 用户 PATCH 的 media 非 `image/*`
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 含 `media_id`

#### Scenario: 清空头像成功

- **WHEN** 认证用户 PATCH `avatar_media_id` 为 null
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 `avatar_url` SHALL 为 null

### Requirement: Current user profile endpoint

系统 SHALL 提供需认证的 `GET /users/me`；响应 SHALL 包含 `id`、`phone`、`email`（可 null）、`nickname`、`avatar_url`（可 null，由 `avatar_media_id` resolve）、`created_at`；SHALL NOT 包含 `password_hash` 或 `avatar_media_id`。

#### Scenario: 有效 token 返回当前用户

- **WHEN** 客户端携带有效 access token 请求 `GET /users/me`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 包含 `id`（UUID 字符串）、`phone`、`email`（可为 null）、`nickname`、`avatar_url`（可为 null）、`created_at`

#### Scenario: 无 token 或 token 无效返回 401

- **WHEN** 客户端未携带 `Authorization` 或 token 无效/过期
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: token 有效但用户不存在返回 401

- **WHEN** token 中 `sub` 对应用户已从数据库删除
- **THEN** 响应状态码 SHALL 为 401

## ADDED Requirements

### Requirement: Users avatar media reference

`users` 表 SHALL 含可空列 `avatar_media_id`（FK → `media_assets.id`）。

#### Scenario: Migration adds avatar_media_id

- **WHEN** 执行 Alembic upgrade head
- **THEN** `users` SHALL 含 `avatar_media_id` 列
- **AND** SHALL NOT 含仅用于外链头像的冗余 URL 列
