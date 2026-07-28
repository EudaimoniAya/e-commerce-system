## 1. 配置、契约与基础模块

- [x] 1.1 扩展 `Settings`（`sms_otp_ttl_seconds`、`sms_send_cooldown_seconds`、`sms_daily_send_limit`、`sms_verify_fail_limit`、可选 `sms_otp_fixed_code`）；更新 `.env.example` / `.env.test`
- [x] 1.2 实现 `app/user/phone.py`（`normalize_phone`）；单元测试 `tests/unit/user/test_phone.py`
- [x] 1.3 **定义 Schema DTO（接口契约）**：`SmsSendRequest`、`SmsRegisterRequest`、`SmsLoginRequest`、`LoginRequest`、`UserProfileUpdateRequest`、`UserResponse`（`phone: str`、`email: str | None`）

## 2. TDD — 失败测试（红）

> **顺序**：§1.3 完成后方可写 §2 测试。

- [x] 2.1 扩展 `tests/support/builders.py`：`unique_phone`、`build_sms_send_request`、`build_sms_register_request`、`build_sms_login_request`、`build_login_request`
- [x] 2.2 扩展 `tests/support/results.py` 与 `tests/support/contexts.py`：
  - 新增 `SmsSendResult`、`**SmsRegisterResult`**、`**SmsLoginResult**`（OTP 登录，区别于密码 `LoginResult`）
  - `**LoginResult**`：`identifier`（手机号 + 密码）
  - `**AuthContext` / `ShopOwnerContext**`：含 `**phone**`
- [x] 2.3 重写 `tests/support/helper/auth.py`：`send_sms_otp`、`register_user_via_otp` → `/auth/sms/register`、`login_user_via_otp` → `/auth/sms/login`
- [x] 2.4 按 spec 编写 `tests/user/test_sms_send.py`（成功 200、格式非法 422、冷却 429）；**不编写**实现
- [x] 2.5 按 spec 编写 `tests/user/test_sms_register.py`（201、phone 已存在 422、缺 password 422、OTP 错 422、默认昵称、fail 计数复位）；**不编写**实现
- [x] 2.6 按 spec 编写 `tests/user/test_sms_login.py`（200、用户不存在 422 同 OTP 错文案、禁用 403、fail 计数复位）；**不编写**实现
- [x] 2.7 重写 `tests/user/test_login.py`（identifier+password 200、`INVALID_CREDENTIALS`、禁用 403）
- [x] 2.8 重写 `tests/user/test_register.py` 为 `/auth/register` 404；并断言旧统一点 `**/auth/sms/verify`** 404（该端点已随 register/login 拆分移除，勿与 `/auth/sms/register`、`/auth/sms/login` 混淆）；更新 `test_me.py`、新增 `test_profile.py`
- [x] 2.9 运行 `devbox run -- task redis:up` + `devbox run -- task test tests/user/`，确认 user 相关测试失败（红）

## 3. 迁移与 ORM

- [x] 3.1 更新 `app/user/models.py`（`phone`、`email` nullable、`password_hash` nullable）；新增 migration `008_user_phone`
- [x] 3.2 migration 回填 admin seed `phone='13800000000'`
- [x] 3.3 更新 `tests/support/db/user.py`：`seed_active_user` / `seed_inactive_user` 支持可选 `**phone**`

## 4. SMS OTP 服务（绿 · 基础设施）

- [x] 4.1 实现 `app/user/sms.py`：`SmsOtpService`（send、GETDEL consume、限流、register/login 成功后 DEL `sms:verify_fail:{phone}`）
- [x] 4.2 实现 `app/user/deps.py` 注入 `SmsOtpService`；wire `get_redis()`

## 5. user 域业务（绿）

- [x] 5.1 扩展 `app/user/repository.py`（`get_by_phone`、`create` 支持 phone、`update_profile`）
- [x] 5.2 扩展 `app/user/service.py`（`register_via_sms`、`login_via_sms`、password login；login 失败 dict detail `INVALID_CREDENTIALS`；扩展 `_to_user_response`）
- [x] 5.3 更新 `app/user/router.py`（`/auth/sms/send`、`/auth/sms/register`、`/auth/sms/login`、修改 `/auth/login`、移除 `/auth/register`、移除 `/auth/sms/verify`、`PATCH /users/me`）

## 6. 测试基建与全项目迁移

- [x] 6.1 更新 `tests/conftest.py` fixture（OTP register 路径、`AuthContext.phone`）
- [x] 6.2 迁移 catalog / ordering 等 integration 测试 helper 调用
- [x] 6.3 更新 `tests/infra/test_error_handlers.py`、`tests/user/test_user_summary.py`

## 7. 本地验证与 CI

- [x] 7.1 运行 `devbox run -- task migrate` 后 `devbox run -- task ci` 全绿；curl send → register → login → PATCH /users/me
- [x] 7.2 更新 `README.md`、`docs/architecture.md`

## 8. 文档与 DoD

- [ ] 8.1 确认 DoD；可执行 `/opsx:archive`

> **Apply 约定**：§1.3 → §2（红）→ §3–§5（绿）；DB/Redis 使用 `devbox run --`。

