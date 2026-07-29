## Context

`infra-database` 已交付 MySQL、Alembic、异步 Session、readiness 与 CI integration 测试。`app/main.py` 仅挂载 health/readiness，尚无业务域。架构规划首个业务垂直切片为 **user 域认证**；catalog/ordering 后续依赖 `user_id` 与 JWT 鉴权依赖。

约束来自 explore 决策：

- 单体多域：`user` 域内分层；`infra` 不得 import 业务域（`.cursor/rules/cross-domain-imports.mdc`）
- JWT 编解码在 `infra`；`get_current_user`（查库）在 `user/deps.py`
- 用户主键：**UUID v4**；JWT `sub` 为 UUID 字符串
- 本 change **仅 access token**（30 分钟）；refresh 留给后续 change，上线 main 前补齐
- 未来 PostgreSQL/pgvector 将使用 **独立 Base 与 Alembic 入口**；本 change 不引入

## Goals / Non-Goals

**Goals:**

- 实现 `POST /auth/register`、`POST /auth/login`、`GET /users/me` 可演示闭环
- 建立 JWT 鉴权依赖链：`get_current_user_id`（infra）→ `get_current_user`（user）
- `users` 表 Alembic migration；Base `naming_convention`；TDD integration 测试全绿
- 扩展 Settings、`.env.example`、CI `JWT_SECRET_KEY`
- 更新 README 阶段描述；新增 ADR《单例与线程锁在 FastAPI 中的适用场景》（个人学习，不进 OpenSpec）

**Non-Goals:**

- refresh token、登出、token 黑名单、OAuth 表单登录
- 商家/店铺、superuser、用户资料修改、禁用用户管理 API
- catalog 公开 API、Faker 种子数据

## Decisions

### 1. API 路由与请求/响应格式

| 方法 | 路径 | 鉴权 | 请求体 |
|------|------|------|--------|
| POST | `/auth/register` | 无 | JSON `{ "email", "password", "nickname"? }` |
| POST | `/auth/login` | 无 | JSON `{ "email", "password" }` |
| GET | `/users/me` | Bearer | — |

**登录/注册成功响应**（OAuth2 惯例 + 用户信息）：

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "nickname": "用户_20260713142035",
    "created_at": "2026-07-13T14:20:35"
  }
}
```

- 注册返回 **201**；登录返回 **200**
- 业务逻辑错误（重复邮箱、凭据错误）→ **422**
- `is_active=false` 登录 → **403**（已识别身份但不允许进入）
- 鉴权失败（无 token/无效/过期）→ **401**

**理由**：`/auth/*` 聚合认证动作，`/users/me` 表资源归属；JSON 请求体便于结构化日志；`expires_in` 便于客户端调度刷新（后期）。

### 2. 模块布局

```text
app/
├── main.py                      # 挂载 auth router + users router
├── infra/
│   ├── config.py                # 扩展 jwt_* 字段
│   ├── database.py              # Base + naming_convention
│   └── auth.py                  # PyJWT、OAuth2PasswordBearer、get_current_user_id
└── user/
    ├── router.py                # /auth/register, /auth/login, /users/me
    ├── service.py               # register、login、authenticate；pwdlib 哈希
    ├── repository.py            # CRUD；只收 password_hash
    ├── models.py                # User ORM
    ├── schemas.py               # RegisterRequest、LoginRequest、TokenResponse、UserResponse
    └── deps.py                  # get_current_user（Depends get_current_user_id + repo）

alembic/
├── env.py                       # import app.user.models
└── versions/
    └── 002_create_users.py

tests/
├── conftest.py                  # auth helper + authenticated_user fixture
└── user/
    ├── test_register.py
    ├── test_login.py
    └── test_me.py
```

**跨域边界**：catalog/ordering 仅需 `user_id` 时 `Depends(get_current_user_id)` from `app.infra.auth`；需要用户展示字段时 import `app.user.deps.get_current_user` 或调 `user.service`（不 import repository/models）。

### 3. JWT：PyJWT + claims

```python
payload = {
    "iss": settings.jwt_issuer,       # "e-commerce-system"
    "sub": str(user.id),              # UUID 字符串
    "iat": int(now.timestamp()),
    "exp": int(expire.timestamp()),
    "typ": "access",
}
```

- 库：**PyJWT**；算法 HS256
- 过期：默认 30 分钟（`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30`）
- 鉴权失败统一 **401**（非 403）；403 保留给 `is_active=false` 登录场景

**不用 Singleton AuthHandler**：JWT 为无状态函数，见 ADR《单例与线程锁…》。

### 4. 用户模型（user 域归属）

表名 `users`：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | `CHAR(36)` / `Uuid` | UUID v4，service 层 `uuid.uuid4()` |
| `email` | `VARCHAR(255)` UNIQUE | Pydantic `EmailStr` |
| `password_hash` | `VARCHAR(255)` | pwdlib 输出 |
| `nickname` | `VARCHAR(64)` | 可选；默认 `用户_{YYYYMMDDHHmmss}` 毫秒可用 `%Y%m%d%H%M%S` + 毫秒三位 |
| `is_active` | `BOOLEAN` | 默认 `true` |
| `created_at` | `DATETIME` | server default |
| `updated_at` | `DATETIME` | on update |

ORM：`app/user/models.py` 继承 `app.infra.database.Base`。

### 5. 密码：pwdlib（service 层）

```python
from pwdlib import PasswordHash
_hasher = PasswordHash.recommended()

# register: _hasher.hash(password)
# login:    _hasher.verify(password, user.password_hash)
```

- 长度规则：8–32 位（Pydantic `Field(min_length=8, max_length=32)`）
- repository **只**接收 `password_hash`，不见明文

### 6. Base naming_convention

在 `app/infra/database.py` 的 `Base` 上设置：

```python
metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})
```

### 7. Settings 字段（snake_case）

```python
jwt_secret_key: str
jwt_issuer: str = "e-commerce-system"
jwt_algorithm: str = "HS256"
jwt_access_token_expire_minutes: int = 30
```

`.env.example` 补充 `JWT_SECRET_KEY` 等；CI workflow 注入固定测试密钥。

### 8. 依赖链

```text
GET /users/me
  → Depends(get_current_user)          # user/deps.py
      → Depends(get_current_user_id)   # infra/auth.py，解析 JWT
      → user.repository.get_by_id()    # 域内查库
      → UserResponse                   # 不含 password_hash
```

`infra` **不得** import `user.repository`；查库只在 `user/deps.py`。

### 9. 测试策略

- 严格 TDD：先写 `tests/user/`（`@pytest.mark.integration`），再实现
- `conftest.py` 提供 helper（`unique_email`、`auth_headers`、`register_user`、`login_user`）与 `authenticated_user` fixture（注册成功并返回 token/headers）
- **HTTP 集成测试统一 `httpx.AsyncClient + ASGITransport`**（不用 Starlette `TestClient`）：与 pytest-asyncio 共用同一 event loop，避免全局 `AsyncEngine` 跨 Portal 双 loop 冲突；详见 ADR《集成测试 AsyncClient 与 Event Loop 线程冲突》
- integration 测试前后 `reset_engine()`；`test_get_db` 使用独立 engine，不污染全局单例
- 覆盖：注册成功/重复 422、登录成功/错误 422/inactive 403、me 200/401
- CI：migrate 后跑 pytest；设置 `JWT_SECRET_KEY`

### 10. 未来 AI 库独立 Base

本 change 仅 MySQL 单 `Base` + 单 Alembic。后期 PostgreSQL 将增加 `app/infra/ai_db.py`（独立 `AiBase`）与 `alembic_ai/`，与 business migration 分离；**本 change 不引入**。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 无 refresh token，30 分钟后需重新登录 | 开发期可 `.env` 调大过期时间；上线前 `user-auth-refresh` change |
| UUID 主键索引略大于 BIGINT | MVP 规模可忽略；外键统一 UUID |
| JSON 登录非 OAuth2 表单，Swagger「Authorize」体验略差 | `OAuth2PasswordBearer` 仍用于 Bearer 提取；文档注明 login 用 JSON |
| 默认昵称时间戳碰撞（极低概率） | 可接受；后期允许用户改昵称 |
| TestClient 与全局 AsyncEngine 跨 event loop 冲突 | 集成测试统一 `httpx.AsyncClient`；integration 前后 `reset_engine()`；见 ADR |

## Migration Plan

1. `alembic upgrade head` 新增 `002_create_users`
2. 回滚：`alembic downgrade -1` 删除 `users` 表
3. 现有 `_infra_migration_smoke` 与 health/readiness 不受影响

## Open Questions

（无阻塞项；下列已在 proposal 决策中关闭）

- ~~注册后是否返回 token~~ → 是
- ~~路由前缀~~ → `/auth/*` + `/users/me`
- ~~密码库~~ → pwdlib
