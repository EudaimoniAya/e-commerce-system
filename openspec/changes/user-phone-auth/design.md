## Context

`user-auth` 当前以 `POST /auth/register`（email + password）与 `POST /auth/login`（email + password）为唯一身份路径；`users` 表主键为 UUID，`email` UNIQUE NOT NULL，`password_hash` NOT NULL。catalog / ordering 等域通过 `infra.auth.get_current_user_id` 解析 JWT `sub`（UUID），跨域 FK 均为 `user_id`，**不**依赖 email 或 phone。

`infra-redis` 已交付：`get_redis()`、`REDIS_URL`、dev/test 逻辑库隔离、CI Redis service container。本 change 在 **user 域**消费 Redis 存储短信 OTP，**不**新增 infra 模块。

约束：

- user 域 SHALL 通过 `app/infra/redis.get_redis` 访问 Redis；**禁止**业务域自行 `Redis.from_url`
- 跨域协作仍只认 `user.id`；catalog / ordering **不**修改
- integration 测试使用 `AsyncClient`；DB/Redis 命令 `devbox run --` 包装
- TDD：先写 spec 场景对应测试（红），再实现（绿）；**Schema DTO 为接口契约**，在写 integration 测试前定义（见 tasks §1.3），不属于业务实现

## Goals / Non-Goals

**Goals:**

- 手机号取代 email 成为主登录标识；注册路径为 **SMS OTP + password**（`POST /auth/sms/verify`）
- 日常登录：**手机号 + 密码** 或 **手机号 + OTP**（换设备/异地）
- Redis 存储 OTP（GETDEL 原子消费）；dev/test Mock SMS Provider
- `users` 表：`phone` UNIQUE nullable（OAuth 预留）、`email` UNIQUE nullable（资料）、`password_hash` nullable
- `PATCH /users/me` 更新可选 `email`、`nickname`
- 移除 `POST /auth/register`；测试 helper 全量迁移 OTP 注册
- design 记录 OAuth / 账号绑定 / 合并的 forward compatibility（`user.id` 为 canonical）

**Non-Goals:**

- 真实 SMS 网关、修改密码、换绑手机、邮箱验证、OAuth 实现、账号合并 API
- 修改 JWT / `infra-auth`、catalog / ordering 业务 API
- 国际化手机号（仅 +86 normalize 为 11 位）

## Decisions

### 1. 主键：`user.id`（UUID）不变；phone 为业务主标识

**选择**：保留 UUID PK；新增 `users.phone` UNIQUE nullable；OTP 注册路径 **MUST** 写入规范化 phone。

**理由**：ordering / catalog FK 与 JWT `sub` 无需迁移；phone 作 natural key 供登录查询。

**备选**：phone 作 DB PK（否决：全库 FK 迁移成本高）。

### 2. 注册：仅 `POST /auth/sms/verify`（移除 `/auth/register`）

**选择**：

1. `POST /auth/sms/send` `{ phone }` — 发 OTP
2. `POST /auth/sms/verify` — 新用户：`{ phone, code, password, nickname? }` → **201**；已有用户：`{ phone, code }` → **200**

新用户 verify **MUST** 含符合 8–32 位规则的 `password`；service 写入 `password_hash`。

**理由**：注册三件套（手机 + 验证码 + 密码）；与「验证码登录即注册」合一端点，靠「用户是否已存在」分支。

**备选**：独立 register 端点（否决：重复 send/verify 逻辑）。

### 3. 登录双路径

| 路径 | API | 条件 |
|------|-----|------|
| 密码 | `POST /auth/login` `{ identifier, password }` | `password_hash IS NOT NULL`；identifier 为规范化 11 位手机号 |
| OTP | send → verify `{ phone, code }` | 用户已存在；无 password 字段 |

**理由**：日常密码登录；换设备 OTP 无需改密。

**错误文案**：密码失败统一 `Invalid phone or password`，不区分不存在/无密码/密码错。实现 SHALL 使用 dict detail 以返回语义化 `error.code`：

```python
HTTPException(
    status_code=422,
    detail={"code": "INVALID_CREDENTIALS", "message": "Invalid phone or password"},
)
```

### 4. 邮箱：仅资料，不参与登录

**选择**：`email` UNIQUE nullable；`PATCH /users/me` 可设/清空；**无**邮箱登录。

**理由**：国内电商惯例；避免与 future OAuth email 冲突。

### 5. 手机号规范化

**选择**：模块 `app/user/phone.py`（或等价）提供 `normalize_phone(raw) -> str | None`：

- 去空格、去 `+86` / `86` 前缀
- 校验 `^1[3-9]\d{9}$`
- DB 与 Redis key 均存规范化 11 位

**Redis key**：`sms:otp:{normalized_phone}`

### 6. Redis OTP 存储与限流

| Key | 值 | TTL |
|-----|-----|-----|
| `sms:otp:{phone}` | 6 位数字字符串 | 300s |
| `sms:cooldown:{phone}` | `1` | 60s |
| `sms:daily:{phone}:{YYYYMMDD}` | 计数 | 86400s |
| `sms:verify_fail:{phone}` | 失败计数 | 900s |

**消费**：`GETDEL sms:otp:{phone}`（Redis 8，不用 Lua）。

**验证成功复位**：`POST /auth/sms/verify` 成功（注册或 OTP 登录）后，SHALL `DEL sms:verify_fail:{phone}`，避免用户先失败后成功、却在锁定窗口内无法再次 verify。

**参数**（Settings 或常量，可 env 覆盖）：

- `sms_otp_ttl_seconds` 默认 300
- `sms_send_cooldown_seconds` 默认 60
- `sms_daily_send_limit` 默认 10
- `sms_verify_fail_limit` 默认 5

**测试**：`.env.test` 可选 `SMS_OTP_FIXED_CODE`；MockSmsProvider 不真发短信。

### 7. Send 防枚举

**选择**：phone 格式合法且未触发限流时，**无论用户是否存在**，返回相同成功响应（**200**，无 body；保留未来扩展 `retry_after` 等字段的空间）。

**理由**：防止通过 send 响应枚举注册用户。

### 8. 模块划分（user 域）

```
app/user/
├── phone.py           # normalize_phone
├── sms.py             # SmsOtpService（send/consume/rate limit）、SmsProvider Protocol、MockSmsProvider
├── router.py          # /auth/sms/*, /auth/login, /users/me, PATCH /users/me
├── service.py         # UserService（verify/register/login/update_profile）
├── repository.py      # get_by_phone, create, update
├── models.py          # User ORM
├── schemas.py         # DTO
└── deps.py            # 不变 + 可选 get_sms_service
```

**跨域**：无；Redis 仅 infra `get_redis()`。

### 9. Admin seed

**选择**：migration `008` 或修订 seed 逻辑：admin 用户 `phone='13800000000'`（seed 常量），保留 email `114514yyut@qq.com` 与 password；`login_admin` helper 改手机号 + 密码。

### 10. Forward Compatibility：OAuth / 绑定 / 合并

**本 change 不建表**；design 约束供下一 change（如 `user-oauth`）沿用：

```
┌─────────────────────────────────────────┐
│  users.id (UUID) — canonical 锚点      │
│  phone / email / password_hash 可空    │
└─────────────────┬───────────────────────┘
                  │ 1:N（未来）
┌─────────────────▼───────────────────────┐
│  user_auth_identities（未来表）          │
│  user_id, provider, provider_uid        │
│  UNIQUE(provider, provider_uid)         │
└─────────────────────────────────────────┘
```

**原则**：

1. 跨域、JWT、订单/店铺 FK **只认** `user.id`
2. `users` 表 **不** 存 `wechat_openid` 等 OAuth 列
3. 凭证查找集中在 `UserRepository`（未来扩展 `get_by_identity`）
4. 合并 = 将 identity 行挂到 canonical `user.id`，可选迁移业务 FK
5. OAuth 用户可 `phone=NULL`；OTP 注册路径仍强制 phone

**phone 存放**：过渡期 `users.phone` 为一等公民；OAuth change 可引入 identity 表并逐步统一。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| **BREAKING** 移除 email 注册/登录 | proposal 标注；README 更新 curl 示例 |
| 全项目 `register_user` helper 依赖 email | tasks 专节迁移 support + conftest |
| SMS 轰炸 | cooldown + daily limit + verify_fail limit |
| OTP 并发双消费 | GETDEL 原子 |
| Redis 不可用 | readiness 已有 redis check；send/verify 失败返回 503 或 422（spec 定） |
| `phone` nullable 与「OTP 必有 phone」 | service 层 invariant，非 DB NOT NULL |
| 测试需 Redis | integration 标记；CI 已有 redis service |

## Migration Plan

1. Alembic `008_user_phone`：`ADD phone VARCHAR(20) UNIQUE NULL`；`MODIFY email NULL`；`MODIFY password_hash NULL`
2. 数据：现有行（含 admin seed）回填 admin `phone='13800000000'`
3. 部署：migrate → 部署新代码 → 旧 `/auth/register` 404
4. 回滚：downgrade migration + 回滚代码（开发环境；生产需评估已注册 phone 用户）

## Open Questions

（无 — explore 阶段已闭合。）
