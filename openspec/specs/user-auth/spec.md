# user-auth

## Purpose

用户域认证垂直切片：注册、JSON 登录、JWT access token、`GET /users/me` 与 `users` 表（含 `is_admin` 平台管理员标识）；为 catalog/ordering 等后续域提供 `user_id` 与鉴权依赖。

## Requirements

### Requirement: User registration with immediate token

系统 SHALL 提供 `POST /auth/register`，接受 JSON 请求体（`email`、`password`）；注册成功 SHALL 创建用户并立即返回 access token，无需二次登录。

#### Scenario: 注册成功返回 token 与用户资料

- **WHEN** 客户端提交有效且未注册的 `email` 与符合长度规则的 `password`
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 JSON SHALL 包含 `access_token`、`token_type`（值为 `bearer`）、`expires_in`（秒）
- **AND** 响应体 SHALL 包含 `user` 对象（含 `id`、`email`、`nickname`、`created_at`）
- **AND** `user` 对象 SHALL NOT 包含 `password` 或 `password_hash`

#### Scenario: 邮箱已注册返回 422

- **WHEN** 客户端提交的 `email` 已存在于 `users` 表
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON（顶层键 `error`）

#### Scenario: 密码长度不合规返回 422

- **WHEN** 客户端提交的 `password` 长度小于 8 或大于 32
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 未提供昵称时使用默认昵称

- **WHEN** 注册请求未包含 `nickname` 或 `nickname` 为空
- **THEN** 系统 SHALL 将 `nickname` 设为 `用户_<注册时毫秒级时间戳>`（例如 `用户_20260713142035`）

### Requirement: User login with JSON body

系统 SHALL 提供 `POST /auth/login`，接受 JSON 请求体（`email`、`password`）；验证成功 SHALL 返回 access token。

#### Scenario: 登录成功返回 token

- **WHEN** 客户端提交正确 `email` 与 `password` 且用户 `is_active` 为 true
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 包含 `access_token`、`token_type`（`bearer`）、`expires_in`
- **AND** 响应体 SHALL 包含 `user` 对象（同注册成功时的字段约束）

#### Scenario: 邮箱不存在返回 422

- **WHEN** 客户端提交的 `email` 不存在于 `users` 表
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON（顶层键 `error`）

#### Scenario: 密码错误返回 422

- **WHEN** 客户端提交的 `email` 存在但 `password` 不正确
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON（顶层键 `error`）
- **AND** 响应 SHALL NOT 区分「邮箱不存在」与「密码错误」（防止用户枚举）

#### Scenario: 用户已禁用返回 403

- **WHEN** 客户端提交正确凭据但对应用户 `is_active` 为 false
- **THEN** 响应状态码 SHALL 为 403

### Requirement: Current user profile endpoint

系统 SHALL 提供需认证的 `GET /users/me`，作为 auth 烟雾端点与用户资料查询；该端点 SHALL 使用 Bearer access token。

#### Scenario: 有效 token 返回当前用户

- **WHEN** 客户端携带有效 access token 请求 `GET /users/me`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 包含 `id`（UUID 字符串）、`email`、`nickname`、`created_at`
- **AND** SHALL NOT 包含 `password_hash`

#### Scenario: 无 token 或 token 无效返回 401

- **WHEN** 客户端未携带 `Authorization` 或 token 无效/过期
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: token 有效但用户不存在返回 401

- **WHEN** token 中 `sub` 对应用户已从数据库删除
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Users table with UUID primary key

系统 SHALL 在 **user 域** 拥有 `users` 表；主键 SHALL 为 UUID v4（应用层生成，非自增整数）。

#### Scenario: 用户记录包含必需字段

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`email`（唯一）、`password_hash`、`nickname`、`is_active`（默认 true）、`is_admin`（默认 false）、`created_at`、`updated_at`
- **AND** `email` SHALL 有唯一约束

### Requirement: Platform administrator flag on users

系统 SHALL 在 `users` 表提供 `is_admin` 列（BOOLEAN，NOT NULL，默认 false），用于标识平台管理员身份；migration `003` SHALL seed 至少一名 `is_admin=true` 的用户。

#### Scenario: 用户表包含 is_admin 列

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列 `is_admin`（BOOLEAN，默认 false）

#### Scenario: Seed 管理员存在

- **WHEN** 执行 migration `003` 至 head 后查询 `users` 表
- **THEN** SHALL 存在 `email` 为 `114514yyut@qq.com` 且 `is_admin` 为 true 的用户记录
- **AND** 该用户 `password_hash` SHALL 为 pwdlib 哈希（非明文存储）

### Requirement: User domain layered structure

user 域 SHALL 采用 router → service → repository → model + schemas 分层；密码哈希 SHALL 在 service 层完成，repository SHALL 只接收 `password_hash`。

#### Scenario: 跨域不得 import user ORM

- **WHEN** 其他业务域需要用户标识
- **THEN** SHALL 使用 `infra` 提供的 `get_current_user_id` 或 user 域公开的 schema/service
- **AND** SHALL NOT import `app.user.models` 或 `app.user.repository`

### Requirement: User routes mounted on application

系统 SHALL 在 `app/main.py` 挂载 auth 与 users 路由。

#### Scenario: 应用处理 auth 请求

- **WHEN** 测试客户端请求 `POST /auth/register` 或 `POST /auth/login` 或 `GET /users/me`
- **THEN** 请求 SHALL 由 FastAPI 应用处理（非 404）

### Requirement: Admin authorization dependency

user 域 SHALL 在 `app/user/deps.py` 提供 `require_admin` FastAPI 依赖：解析 JWT 得到 `user_id` 并查库；当用户 `is_admin` 不为 true 时 SHALL 返回 **403**；无 token 或 token 无效 SHALL 返回 **401**；用户不存在 SHALL 返回 **401**。

#### Scenario: 管理员通过鉴权

- **WHEN** 已认证且 `is_admin=true` 的用户请求依赖 `require_admin` 的端点
- **THEN** 依赖 SHALL 返回该用户 ID（或继续处理请求）

#### Scenario: 非管理员返回 403

- **WHEN** 已认证但 `is_admin=false` 的用户请求依赖 `require_admin` 的端点
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求依赖 `require_admin` 的端点
- **THEN** 响应状态码 SHALL 为 401

### Requirement: User summary for cross-domain read

user 域 SHALL 提供跨域只读 DTO `UserSummary`，字段 SHALL 为 `id`（UUID 字符串）与 `nickname`；SHALL NOT 包含 `email` 或 `password_hash`。`UserService` SHALL 提供 `get_user_summary(user_id)`：用户存在且 `is_active=true` 时返回 `UserSummary`；用户不存在时 SHALL 抛出 **404**；`is_active=false` 时 SHALL 抛出 **422**。

#### Scenario: 有效用户返回摘要

- **WHEN** ordering 或其他域调用 `get_user_summary` 且用户存在且 `is_active=true`
- **THEN** SHALL 返回 `UserSummary` 含 `id` 与 `nickname`
- **AND** SHALL NOT 包含 email

#### Scenario: 用户不存在返回 404

- **WHEN** 调用 `get_user_summary` 且 `user_id` 不存在
- **THEN** SHALL 抛出 HTTP 404

#### Scenario: 用户禁用返回 422

- **WHEN** 调用 `get_user_summary` 且用户 `is_active=false`
- **THEN** SHALL 抛出 HTTP 422
