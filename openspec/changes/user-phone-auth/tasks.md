## 1. 配置、契约与基础模块

- [ ] 1.1 扩展 `Settings`（`sms_otp_ttl_seconds`、`sms_send_cooldown_seconds`、`sms_daily_send_limit`、`sms_verify_fail_limit`、可选 `sms_otp_fixed_code`）；更新 `.env.example` / `.env.test`
- [ ] 1.2 实现 `app/user/phone.py`（`normalize_phone`）；单元测试 `tests/unit/user/test_phone.py`
- [ ] 1.3 **定义 Schema DTO（接口契约，非业务逻辑）**：扩展 `app/user/schemas.py` — `SmsSendRequest`、`SmsVerifyRequest`、`LoginRequest`（`identifier` + `password`）、`UserProfileUpdateRequest`、`UserResponse`（`phone: str`、`email: str | None`）；供 §2 builders/helpers 与测试 import

## 2. TDD — 失败测试（红）

> **顺序**：§1.3 完成后方可写 §2 测试，避免 ImportError 导致「无法收集」而非「断言失败」。

- [ ] 2.1 扩展 `tests/support/builders.py`：`unique_phone`、`build_sms_send_request`、`build_sms_verify_request`、`build_login_request`（identifier）
- [ ] 2.2 扩展 `tests/support/results.py` 与 `tests/support/contexts.py`：
  - 新增 `SmsSendResult`；`RegisterResult` → **`SmsVerifyResult`**（`status_code`、`body`、`phone`、`password`）
  - **`LoginResult`**：`email` → **`identifier`**（即 phone）
  - **`AuthContext`**：新增 **`phone`**；保留 `email`（可选 profile）
  - **`ShopOwnerContext`**：新增 **`phone`**；保留 `email`（可选）
- [ ] 2.3 重写 `tests/support/helper/auth.py`：`send_sms_otp`、`register_user_via_otp`（返回 `SmsVerifyResult`）、`login_user`（identifier+password）、`login_user_via_otp`；更新 `login_admin` 用手机号
- [ ] 2.4 按 spec 编写 `tests/user/test_sms_send.py`（成功 200、格式非法 422、冷却 429）；**不编写**实现
- [ ] 2.5 按 spec 编写 `tests/user/test_sms_verify.py`（新用户 201、缺 password 422、老用户 200、OTP 错 422、禁用 403、verify 成功复位 fail 计数、默认昵称）；**不编写**实现
- [ ] 2.6 重写 `tests/user/test_login.py`（identifier+password 200、凭据无效 422 且 `error.code=INVALID_CREDENTIALS`、禁用 403）；删除 email 登录用例
- [ ] 2.7 重写 `tests/user/test_register.py` 为 `/auth/register` 404；更新 `tests/user/test_me.py`（断言 **`phone`**、`email` 可 null）、新增 `test_profile.py`（PATCH /users/me）
- [ ] 2.8 运行 `devbox run -- task redis:up` + `devbox run -- task test tests/user/`，确认 user 相关测试失败（红）

## 3. 迁移与 ORM

- [ ] 3.1 更新 `app/user/models.py`（`phone`、`email` nullable、`password_hash` nullable）；新增 migration `008_user_phone`
- [ ] 3.2 migration 回填 admin seed `phone='13800000000'`；更新 `tests/support/helper/auth.py` 中 admin 常量
- [ ] 3.3 更新 `tests/support/db/user.py`：`seed_active_user` / `seed_inactive_user` 支持可选 **`phone`** 参数，INSERT 含 `phone` 列

## 4. SMS OTP 服务（绿 · 基础设施）

- [ ] 4.1 实现 `app/user/sms.py`：`SmsOtpService`（send、GETDEL consume、限流、**verify 成功后 DEL `sms:verify_fail:{phone}`**）、`SmsProvider` Protocol、`MockSmsProvider`
- [ ] 4.2 实现 `app/user/deps.py` 注入 `SmsOtpService`；wire `get_redis()`

## 5. user 域业务（绿）

- [ ] 5.1 扩展 `app/user/repository.py`（`get_by_phone`、`create` 支持 phone、`update_profile`）
- [ ] 5.2 扩展 `app/user/service.py`（verify 注册/登录分支、login by identifier、update_profile；**login 失败用 dict detail `INVALID_CREDENTIALS`**；同步扩展 **`_to_user_response`** 含 `phone` / nullable `email`）
- [ ] 5.3 更新 `app/user/router.py`（`/auth/sms/send`、`/auth/sms/verify`、修改 `/auth/login`、移除 `/auth/register`、`PATCH /users/me`）

## 6. 测试基建与全项目迁移

- [ ] 6.1 更新 `tests/conftest.py` fixture（`authenticated_user` / `shop_owner_user` 等走 OTP 注册，`AuthContext.phone` 赋值）
- [ ] 6.2 迁移 catalog / ordering / 其他 integration 测试中的 `register_user` → `register_user_via_otp`
- [ ] 6.3 更新 `tests/infra/test_error_handlers.py` 示例文案（phone）；更新 `tests/user/test_user_summary.py` seed 数据（含 phone）

## 7. 本地验证与 CI

- [ ] 7.1 运行 `devbox run -- task migrate` 后 `devbox run -- task ci` 确认全绿；手动 curl send → verify → login → PATCH /users/me
- [ ] 7.2 确认 CI Redis service 与 `.env.test` 下 OTP 测试通过；更新 `README.md`、`docs/architecture.md`

## 8. 文档与 DoD

- [ ] 8.1 确认 DoD：本地 `task ci` 全绿、文档已更新、旧 `/auth/register` 404；可执行 `/opsx:archive`

> **Apply 约定**：§1.3（Schema 契约）→ §2（红）→ §3–§5（绿）；§2 完成前不得开始 §4–§5；每个 apply 会话建议只完成 1–2 个 task；DB/Redis 命令使用 `devbox run --`。
