# infra-auth

## Purpose

JWT access token 签发与校验、Bearer 鉴权依赖（`get_current_user_id`）；配置经 `Settings` 注入，不查库、不依赖业务域。

## Requirements

### Requirement: JWT access token creation and validation

系统 SHALL 使用 **PyJWT** 签发与校验 access token；算法 SHALL 为 HS256；密钥与过期时间 SHALL 来自 `pydantic-settings` 环境变量配置。

#### Scenario: Token payload 包含标准 claims

- **WHEN** 系统为用户 ID 创建 access token
- **THEN** JWT payload SHALL 包含 `iss`（签发方标识）、`sub`（用户 UUID 字符串）、`iat`、`exp`、`typ`（值为 `access`）

#### Scenario: 有效 token 解码返回用户 ID

- **WHEN** 对未过期且签名正确的 access token 执行解码
- **THEN** 系统 SHALL 返回对应的用户 UUID
- **AND** `typ` SHALL 为 `access`

#### Scenario: 无效或过期 token 解码失败

- **WHEN** token 签名错误、已过期或 `typ` 不是 `access`
- **THEN** 系统 SHALL 拒绝该 token（供依赖层返回 401）

### Requirement: JWT configuration via settings

系统 SHALL 通过 `Settings`（snake_case 字段）加载 JWT 配置，至少包含：

- `jwt_secret_key`（环境变量 `JWT_SECRET_KEY`，长度 SHALL ≥ 32 字节）
- `jwt_issuer`（默认 `e-commerce-system`）
- `jwt_algorithm`（默认 `HS256`）
- `jwt_access_token_expire_minutes`（默认 `30`）

#### Scenario: 缺少 JWT_SECRET_KEY 时失败

- **WHEN** 未设置 `JWT_SECRET_KEY` 且代码路径需要签发或校验 token
- **THEN** 系统 SHALL 以明确错误失败

### Requirement: get_current_user_id dependency

系统 SHALL 在 `app/infra/auth.py` 提供 FastAPI 依赖 `get_current_user_id`，从 `Authorization: Bearer <token>` 解析用户 UUID；该依赖 SHALL NOT 查询数据库，SHALL NOT import 任何业务域模块。

#### Scenario: 合法 Bearer token 返回 UUID

- **WHEN** 受保护路由声明 `Depends(get_current_user_id)` 且请求携带有效 access token
- **THEN** 依赖 SHALL 注入 `uuid.UUID` 类型的用户 ID

#### Scenario: 缺失或非法 token 返回 401

- **WHEN** 请求未携带 Bearer token 或 token 无效/过期
- **THEN** 依赖 SHALL 引发 HTTP 401

### Requirement: OAuth2PasswordBearer scheme

系统 SHALL 使用 `OAuth2PasswordBearer` 提取 Bearer token；`tokenUrl` SHALL 指向 `/auth/login`（文档用途；实际登录接受 JSON 而非表单）。

#### Scenario: OpenAPI 文档包含 Bearer 安全方案

- **WHEN** 访问自动生成的 OpenAPI schema
- **THEN** `GET /users/me` SHALL 声明需要 Bearer 认证
