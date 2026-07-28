## ADDED Requirements

### Requirement: SMS OTP send endpoint

系统 SHALL 提供 `POST /auth/sms/send`，接受 JSON 请求体 `{ "phone": "<原始输入>" }`；SHALL 规范化手机号、生成 6 位数字 OTP、写入 Redis（key `sms:otp:{normalized_phone}`，TTL 默认 300 秒），并通过 Mock SMS Provider 发送（dev/test/CI 不调用真实网关）。

#### Scenario: 发送成功返回统一成功响应

- **WHEN** 客户端提交可规范化为合法 11 位大陆手机号的 `phone` 且未触发限流
- **THEN** 响应状态码 SHALL 为 200
- **AND** Redis SHALL 存在对应 OTP key
- **AND** 响应 SHALL NOT 因该手机号是否已注册而差异（防用户枚举）

#### Scenario: 手机号格式非法返回 422

- **WHEN** 客户端提交的 `phone` 无法规范化为 `^1[3-9]\d{9}$`
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON

#### Scenario: 发送冷却期内重复发送返回 429

- **WHEN** 同一规范化手机号在冷却期（默认 60 秒）内再次请求 send
- **THEN** 响应状态码 SHALL 为 429
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON

#### Scenario: 日发送次数超限返回 429

- **WHEN** 同一规范化手机号当日 send 次数已达上限（默认 10 次）
- **THEN** 响应状态码 SHALL 为 429

### Requirement: SMS OTP register endpoint

系统 SHALL 提供 `POST /auth/sms/register`，接受 JSON 请求体 `{ "phone", "code", "password", "nickname?" }`；SHALL 校验 Redis OTP（**GETDEL** 原子消费）；该 phone **MUST NOT** 已存在；成功 SHALL 创建用户并返回 access token。

#### Scenario: 新用户注册成功返回 201 与 token

- **WHEN** 客户端提交合法 `phone`、`code` 与符合 8–32 位规则的 `password`，且 OTP 正确、该 phone 尚无用户
- **THEN** 响应状态码 SHALL 为 201
- **AND** 响应体 SHALL 包含 `access_token`、`token_type`（`bearer`）、`expires_in`、`user`（含 `id`、`phone`、`email`（可 null）、`nickname`、`created_at`）
- **AND** 系统 SHALL 创建用户并写入 `phone` 与 `password_hash`
- **AND** OTP key SHALL 已被删除（不可复用）

#### Scenario: 手机号已注册返回 422

- **WHEN** 客户端向 `POST /auth/sms/register` 提交的 `phone` 已存在于 `users` 表且 OTP 正确
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON

#### Scenario: 注册缺少 password 或长度不合规返回 422

- **WHEN** register 请求未包含 `password` 或 `password` 长度小于 8 或大于 32
- **THEN** 响应状态码 SHALL 为 422

#### Scenario: 注册 OTP 错误或过期返回 422

- **WHEN** 客户端提交的 `code` 与 Redis 中 OTP 不匹配、OTP 已过期或已被消费
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.message` SHALL 为 `"Invalid or expired verification code"`

#### Scenario: 注册成功后复位验证失败计数

- **WHEN** 客户端 register 成功
- **THEN** Redis key `sms:verify_fail:{normalized_phone}` SHALL 被删除

#### Scenario: 未提供昵称时使用默认昵称

- **WHEN** register 请求未包含 `nickname` 或 `nickname` 为空
- **THEN** 系统 SHALL 将 `nickname` 设为 `用户_<注册时毫秒级时间戳>`

#### Scenario: 注册验证失败次数超限返回 429

- **WHEN** 同一手机号在锁定窗口（默认 15 分钟）内 OTP 验证失败次数达到上限（默认 5 次）
- **THEN** 响应状态码 SHALL 为 429

### Requirement: SMS OTP login endpoint

系统 SHALL 提供 `POST /auth/sms/login`，接受 JSON 请求体 `{ "phone", "code" }`（**不含** `password`）；SHALL 校验 Redis OTP（**GETDEL** 原子消费）；该 phone **MUST** 已存在且 `is_active=true`；成功 SHALL 返回 access token。

#### Scenario: 已有用户 OTP 登录成功返回 200

- **WHEN** 客户端提交合法 `phone` 与正确 `code`，且该 phone 对应用户已存在且 `is_active=true`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 包含 token 与 `user` 对象（字段约束同注册成功）

#### Scenario: OTP 登录时用户不存在返回 422

- **WHEN** 客户端向 `POST /auth/sms/login` 提交的 `phone` 不存在于 `users` 表
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.message` SHALL 为 `"Invalid or expired verification code"`（与 OTP 错误同文案，防枚举）

#### Scenario: OTP 错误或过期返回 422

- **WHEN** 客户端提交的 `code` 与 Redis 中 OTP 不匹配、OTP 已过期或已被消费
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.message` SHALL 为 `"Invalid or expired verification code"`

#### Scenario: OTP 登录时用户已禁用返回 403

- **WHEN** OTP 正确但对应用户 `is_active=false`
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: OTP 登录成功后复位验证失败计数

- **WHEN** 客户端 OTP login 成功
- **THEN** Redis key `sms:verify_fail:{normalized_phone}` SHALL 被删除

#### Scenario: OTP 登录验证失败次数超限返回 429

- **WHEN** 同一手机号在锁定窗口内 OTP 验证失败次数达到上限
- **THEN** 响应状态码 SHALL 为 429

### Requirement: Phone number normalization

系统 SHALL 在 user 域提供手机号规范化：去除空格与 `+86`/`86` 前缀，校验为 11 位中国大陆手机号（`^1[3-9]\d{9}$`）；DB 存储与 Redis key SHALL 使用规范化结果。

#### Scenario: 接受带 +86 前缀的输入

- **WHEN** 客户端提交 `"+8613800138000"`
- **THEN** 规范化结果 SHALL 为 `"13800138000"`

### Requirement: User profile update endpoint

系统 SHALL 提供需认证的 `PATCH /users/me`，允许更新可选资料字段 `email`（`EmailStr`，可 null 清空）与 `nickname`；SHALL NOT 通过本端点修改 `phone` 或 `password`。

#### Scenario: 更新 email 与 nickname 成功

- **WHEN** 认证用户提交合法 `email` 和/或 `nickname`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 SHALL 反映更新后的用户资料

#### Scenario: email 已被其他用户占用返回 422

- **WHEN** 客户端提交的 `email` 已被其他用户占用
- **THEN** 响应状态码 SHALL 为 422

### Requirement: OAuth and account linking forward compatibility

user 域 SHALL 保持 `user.id`（UUID）为全系统身份锚点；SHALL NOT 在 `users` 表增加 OAuth provider 列。凭证查找 SHALL 集中在 `UserRepository`（`get_by_phone` 等），以便未来 `user_auth_identities` 表与账号合并 change 扩展。跨域 SHALL 继续只使用 `user_id`，SHALL NOT 依赖 `phone` 作为 FK。

#### Scenario: 跨域仍使用 user_id

- **WHEN** ordering 或 catalog 域关联用户
- **THEN** SHALL 仅存储与查询 `user.id`（UUID），SHALL NOT 存储 phone

## MODIFIED Requirements

### Requirement: User login with JSON body

系统 SHALL 提供 `POST /auth/login`，接受 JSON 请求体 `{ "identifier": "<手机号>", "password": "<密码>" }`；`identifier` 当前 **仅** 接受规范化后的 11 位大陆手机号（**非**任意字符串，**非**邮箱）；验证成功 SHALL 返回 access token。用户 `password_hash` 为 NULL 时 SHALL 与密码错误同等对待（422，不泄露无密码状态）。

#### Scenario: 登录成功返回 token

- **WHEN** 客户端提交正确 `identifier`（手机号）与 `password` 且用户 `is_active=true` 且 `password_hash` 非空
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 包含 `access_token`、`token_type`（`bearer`）、`expires_in`
- **AND** 响应体 SHALL 包含 `user` 对象（含 `id`、`phone`、`email`（可 null）、`nickname`、`created_at`）

#### Scenario: 凭据无效返回 422

- **WHEN** 客户端提交的 `identifier` 对应用户不存在、或 `password` 不正确、或 `password_hash` 为 NULL
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON
- **AND** `error.code` SHALL 为 `INVALID_CREDENTIALS`
- **AND** `error.message` SHALL 为 `"Invalid phone or password"`
- **AND** SHALL NOT 区分「用户不存在」「无密码」与「密码错误」

#### Scenario: 用户已禁用返回 403

- **WHEN** 客户端提交正确凭据但对应用户 `is_active=false`
- **THEN** 响应状态码 SHALL 为 403

### Requirement: Current user profile endpoint

系统 SHALL 提供需认证的 `GET /users/me`；响应 SHALL 包含 `id`、`phone`、`email`（可 null）、`nickname`、`created_at`；SHALL NOT 包含 `password_hash`。

#### Scenario: 有效 token 返回当前用户

- **WHEN** 客户端携带有效 access token 请求 `GET /users/me`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 包含 `id`（UUID 字符串）、`phone`、`email`（可为 null）、`nickname`、`created_at`

#### Scenario: 无 token 或 token 无效返回 401

- **WHEN** 客户端未携带 `Authorization` 或 token 无效/过期
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: token 有效但用户不存在返回 401

- **WHEN** token 中 `sub` 对应用户已从数据库删除
- **THEN** 响应状态码 SHALL 为 401

### Requirement: Users table with UUID primary key

系统 SHALL 在 **user 域** 拥有 `users` 表；主键 SHALL 为 UUID v4（应用层生成）。表 SHALL 包含 `phone`（VARCHAR，UNIQUE，nullable，OAuth 预留）、`email`（VARCHAR，UNIQUE，nullable，资料字段）、`password_hash`（nullable；SMS register 路径 MUST 写入非空哈希）。

#### Scenario: 用户记录包含必需字段

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`phone`（UNIQUE nullable）、`email`（UNIQUE nullable）、`password_hash`（nullable）、`nickname`、`is_active`（默认 true）、`is_admin`（默认 false）、`created_at`、`updated_at`

### Requirement: Platform administrator flag on users

系统 SHALL 在 `users` 表提供 `is_admin` 列；seed 管理员 SHALL 具有规范化手机号 `13800000000`、email `114514yyut@qq.com` 与 pwdlib 哈希密码。

#### Scenario: 用户表包含 is_admin 列

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列 `is_admin`（BOOLEAN，默认 false）

#### Scenario: Seed 管理员存在且可手机号登录

- **WHEN** 执行 migration 至 head 后查询 `users` 表
- **THEN** SHALL 存在 `phone` 为 `13800000000`、`email` 为 `114514yyut@qq.com`、`is_admin` 为 true 的用户
- **AND** 该用户 `password_hash` SHALL 为 pwdlib 哈希（非明文）

### Requirement: User routes mounted on application

系统 SHALL 在 `app/main.py` 挂载 auth 与 users 路由。

#### Scenario: 应用处理 auth 请求

- **WHEN** 测试客户端请求 `POST /auth/sms/send`、`POST /auth/sms/register`、`POST /auth/sms/login`、`POST /auth/login`、`PATCH /users/me` 或 `GET /users/me`
- **THEN** 请求 SHALL 由 FastAPI 应用处理（非 404）

#### Scenario: 旧注册端点已移除

- **WHEN** 测试客户端请求 `POST /auth/register`
- **THEN** 响应状态码 SHALL 为 404

#### Scenario: 旧统一 verify 端点已移除

- **WHEN** 测试客户端请求 `POST /auth/sms/verify`
- **THEN** 响应状态码 SHALL 为 404

## REMOVED Requirements

### Requirement: User registration with immediate token

**Reason**: 注册路径改为 `POST /auth/sms/send` → `POST /auth/sms/register`（手机号 + OTP + 密码）；不再支持邮箱 + 密码直接注册。

**Migration**: 客户端按用户意图选择 register 或 login Tab，分别调用 `/auth/sms/register` 或 `/auth/sms/login`；集成测试 helper 使用 `register_user_via_otp` / `login_user_via_otp`。
