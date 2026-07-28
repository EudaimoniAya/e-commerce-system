## Why

当前 `user-auth` 以邮箱 + 密码为唯一注册/登录路径，不符合国内电商以手机号为主身份的习惯；验证码、换设备登录等能力也无法在现有模型上扩展。`infra-redis` 已就绪，可在本 change 将 Redis 用于短信 OTP。需要在 catalog/ordering 等域继续扩展前，完成 **手机号主认证** 垂直切片，并为后续第三方 OAuth、账号绑定与合并预留 `user.id` 锚点。

## What Changes

- **BREAKING**：移除 `POST /auth/register`（邮箱 + 密码注册）
- **BREAKING**：`POST /auth/login` 改为 `identifier`（规范化 11 位手机号）+ `password`；不再支持邮箱登录
- 新增 **`POST /auth/sms/send`**：发送短信 OTP（Redis 存储；dev/test 使用 Mock SMS Provider）
- 新增 **`POST /auth/sms/verify`**：
  - 新用户：手机号 + 验证码 + 密码（+ 可选 nickname）→ 注册并返回 token（**201**）
  - 已有用户：手机号 + 验证码 → OTP 登录（**200**；换设备/异地场景）
- 保留 **`POST /auth/login`**：手机号 + 密码日常登录
- 新增 **`PATCH /users/me`**：更新可选资料字段 `email`、`nickname`（邮箱不参与登录）
- **`users` 表**（migration `008`）：新增 `phone`（UNIQUE，nullable，OAuth 预留）；`email` 改为 UNIQUE nullable；`password_hash` 改为 nullable
- OTP 注册路径 **MUST** 写入规范化 `phone` 与 `password_hash`；无密码用户仅能通过 OTP 登录
- Admin seed 补充 seed 手机号；测试 helper 从 `register_user(email)` 迁移为 OTP 注册
- `design.md` 记录 **Forward Compatibility**：未来 `user_auth_identities`、OAuth 绑定与账号合并以 `user.id` 为 canonical

## Non-goals

- **不** 接入真实 SMS 网关（阿里云/腾讯云等）
- **不** 实现修改密码、忘记密码、换绑手机号
- **不** 实现邮箱验证链接或邮箱登录
- **不** 实现第三方 OAuth、账号绑定 API、账号合并 API（仅 architecture 预留）
- **不** 实现图形验证码 / 滑块等人机验证
- **不** 修改 catalog / ordering 业务 API（跨域仍只认 `user.id`）
- **不** 修改 JWT / `infra-auth` 核心机制（`sub` 仍为 UUID）

## Capabilities

### New Capabilities

（无独立新 capability；OTP/SMS 消费属于 user 域扩展，合并在 `user-auth` delta 中。）

### Modified Capabilities

- `user-auth`：注册/登录改为手机号 + OTP/密码；移除邮箱注册与邮箱登录；新增 SMS 端点、`PATCH /users/me`、`users` 表 phone 列与 nullable 约束；更新 seed admin 与错误文案
- `infra-api-errors`：登录失败示例文案由 email 改为 phone（`INVALID_CREDENTIALS` 场景）

## Impact

- **业务域**：**user**（router、service、repository、model、schemas、deps、新增 sms/otp 模块）；**infra** 仅消费已有 `get_redis()`，不新增 infra 模块
- **新增/修改文件**：`app/user/`（含 OTP service、phone normalize）、`alembic/versions/008_*.py`、迁移 `003` seed 补充 phone、`tests/user/`、`tests/support/helper/auth.py`、`tests/support/builders.py`、`tests/conftest.py`、各域 integration 测试 Arrange helper、`README.md`、`docs/architecture.md`
- **API**：移除 `/auth/register`；新增 `/auth/sms/send`、`/auth/sms/verify`；修改 `/auth/login`；新增 `PATCH /users/me`；`GET /users/me` 响应含 `phone`、可选 `email`
- **依赖**：无新增 Python 依赖（Redis、pwdlib、PyJWT 已有）
- **环境**：integration 测试依赖 Redis（`devbox run -- task redis:up`）；可选 `.env.test` 配置 `SMS_OTP_FIXED_CODE`
- **测试**：全项目 `register_user` helper 改为 OTP 路径；`login_admin` 改为手机号 + 密码
