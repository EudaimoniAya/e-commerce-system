## 1. 依赖与配置

- [x] 1.1 在 `pyproject.toml` 添加 `pyjwt`、`pwdlib`、`email-validator`；执行 `uv sync`
- [x] 1.2 扩展 `app/infra/config.py`：`jwt_secret_key`、`jwt_issuer`、`jwt_algorithm`、`jwt_access_token_expire_minutes`；更新 `.env.example`
- [x] 1.3 在 `app/infra/database.py` 为 `Base` 添加 `metadata.naming_convention`（见 design.md §6）

## 2. ADR（个人学习笔记）

- [x] 2.1 编写 `docs/decision/单例与线程锁在FastAPI中的适用场景.md`（JWT 不用 Singleton 的理由；不进 OpenSpec）

## 3. TDD — 失败测试（红）

- [x] 3.1 扩展 `tests/conftest.py`：helper（`unique_email`、`auth_headers`、`register_user`、`login_user`）与 `authenticated_user` fixture（integration）
- [x] 3.2 按 `specs/user-auth/spec.md` 编写 `tests/user/test_register.py`（201、重复 422、密码长度（过长/过短） 422、默认昵称）；**不编写** user 实现
- [x] 3.3 按 `specs/user-auth/spec.md` 编写 `tests/user/test_login.py`（200、邮箱不存在 422、密码错误 422、inactive 403）；**不编写** 实现
- [x] 3.4 按 `specs/user-auth/spec.md` 编写 `tests/user/test_me.py`（200、无 token 401、无效 token 401）；**不编写** 实现
- [x] 3.5 运行 `task db:up` 后 `task test`，确认 `tests/user/` 相关测试失败（红），在 tasks 或 commit 消息中记录预期失败原因

## 4. 迁移与 infra 认证（绿 · 基础）

- [x] 4.1 实现 `app/user/models.py`（UUID 主键 `User` ORM）；`alembic/env.py` 导入 `app.user.models`；新增 migration `002_create_users`
- [x] 4.2 实现 `app/infra/auth.py`（PyJWT 编解码、`OAuth2PasswordBearer`、`get_current_user_id`）；使 token 编解码相关单元逻辑可被测试间接验证

## 5. user 域实现（绿 · 业务）

- [ ] 5.1 实现 `app/user/schemas.py`、`repository.py`、`service.py`（pwdlib 哈希、注册/登录、默认昵称、422/403 规则）
- [ ] 5.2 实现 `app/user/deps.py`（`get_current_user`）与 `router.py`（`/auth/register`、`/auth/login`、`/users/me`）；在 `app/main.py` 挂载路由

## 6. 本地验证与 CI

- [ ] 6.1 运行 `task migrate` 后 `task ci` 确认本地全绿；手动 `curl` 注册、登录、`/users/me`
- [ ] 6.2 更新 `.github/workflows/ci.yml`：注入 `JWT_SECRET_KEY`；确认 migrate + pytest 通过
- [ ] 6.3 push 并确认 GitHub Actions 全绿（`workflow_dispatch` 或 PR）

## 7. 文档与 DoD

- [ ] 7.1 更新 `README.md`（阶段描述改为 user 业务域开发；auth API 演示）与 `docs/architecture.md`（`app/user/` 结构）
- [ ] 7.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿、文档已更新；可执行 `/opsx:archive` 归档

> **Apply 约定**：严格 TDD，§3 完成前不得开始 §4–§5；每个 apply 会话建议只完成 1–2 个 task。

> **§3 红阶段预期失败（2026-07-13 验证）**：`tests/user/` 共 12 项，全部失败，符合 TDD 预期。
> - **11 项**：auth 路由未挂载（`app/main.py` 尚无 `/auth/*`、`/users/me`）→ 响应 **404**，断言期望 201/200/401/422/403。
> - **1 项**（`test_login_inactive_user_returns_403`）：`users` 表未迁移（Task 4.1）→ **ProgrammingError: Table 'ecommerce_test.users' doesn't exist**。
> - 既有 `tests/health/`、`tests/infra/` **9 项通过**。
