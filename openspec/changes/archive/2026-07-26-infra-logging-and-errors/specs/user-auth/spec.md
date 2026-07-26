## MODIFIED Requirements

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
