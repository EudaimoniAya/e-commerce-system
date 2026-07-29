## Why

`infra-database` 已交付 MySQL、Alembic、异步 Session 与 readiness 探针，但尚无业务域与身份认证。后续 catalog、ordering 等域均依赖「已登录用户」与 JWT 鉴权依赖。需要在第一个商品/订单 change 之前完成 **user 域认证垂直切片**，使注册、登录、受保护 API 与 CI integration 测试可演示。

## What Changes

- 新增 **user 业务域**（`app/user/`）：UUID 主键 `users` 表、注册/登录、`GET /users/me`
- 新增 **infra 认证设施**（`app/infra/auth.py`）：PyJWT access token 编解码、`get_current_user_id` 依赖（不查库、不 import 业务域）
- 新增 **user 域鉴权依赖**（`app/user/deps.py`）：`get_current_user`（域内查库，返回 `UserResponse`）
- **API**：
  - `POST /auth/register` — JSON 注册，成功即返回 access token
  - `POST /auth/login` — JSON 登录，返回 access token
  - `GET /users/me` — 需 Bearer token，返回当前用户资料（烟雾端点 + 真实产品能力）
- **JWT claims**：`iss`、`sub`（UUID 字符串）、`iat`、`exp`、`typ`（`access`）；access token 默认 30 分钟
- **密码**：pwdlib 哈希（service 层）；规则 8–32 位；业务逻辑错误（如重复注册）返回 **422**
- **Base** 增加 `MetaData(naming_convention=...)`；`alembic/env.py` 注册 `app.user.models`
- 扩展 **Settings** / `.env.example`：`JWT_SECRET_KEY`、`JWT_ISSUER`、`JWT_ALGORITHM`、`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`
- 扩展 **pytest**：`tests/user/` integration 测试（register、login、me 401/200、inactive 403）
- 扩展 **CI**：注入测试用 `JWT_SECRET_KEY`
- 更新 **README.md** 阶段描述（进入 user 业务域开发）
- 新增 **ADR**（`docs/decision/单例与线程锁在FastAPI中的适用场景.md`）— 个人学习笔记，不进 OpenSpec

## Non-goals

- 不实现 refresh token / 双 token / 登出 / token 黑名单（留给后续 `user-auth-refresh` change；上线 main 前补齐）
- 不实现商家（`is_seller`）、店铺、superuser / admin 后台
- 不实现用户资料修改、邮箱验证、找回密码、禁用用户 API（`is_active=false` 时 login 返回 403，但无管理接口）
- 不实现 catalog 公开商品 API、ordering
- 不引入 PostgreSQL / AI 库独立 Base（design 中记录未来双迁移入口，本 change 不引入）
- 不使用 OAuth2 表单登录（`application/x-www-form-urlencoded`）；统一 JSON 请求体

## Capabilities

### New Capabilities

- `user-auth`：用户注册、登录、当前用户资料（`POST /auth/register`、`POST /auth/login`、`GET /users/me`）；`users` 表与域内分层（router → service → repository → model + schemas + deps）
- `infra-auth`：JWT access token 创建与校验、`OAuth2PasswordBearer`、`get_current_user_id` 依赖；Settings JWT 配置项

### Modified Capabilities

- `infra-database`：共享 `Base` SHALL 配置 `metadata.naming_convention`；Alembic env SHALL 导入业务域模型以注册 metadata

## Impact

- **业务域**：`user`（首个业务限界上下文）、`infra`（auth、config、database Base）
- **新增/修改文件**：`app/user/`（`router.py`、`service.py`、`repository.py`、`models.py`、`schemas.py`、`deps.py`）、`app/infra/auth.py`、`app/infra/config.py`、`app/infra/database.py`、`app/main.py`、`alembic/versions/`（`users` 表 migration）、`alembic/env.py`、`tests/user/`、`tests/conftest.py`（auth helpers）、`.env.example`、`.github/workflows/ci.yml`、`pyproject.toml`、`README.md`、`docs/decision/`
- **API**：新增 `/auth/register`、`/auth/login`、`/users/me`；`/health`、`/health/ready` 不变
- **依赖**：pyjwt、pwdlib、email-validator（Pydantic `EmailStr`）
- **分支**：基于 `dev` 的 `feature/user-auth`
