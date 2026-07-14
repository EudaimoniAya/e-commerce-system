## 1. user 域 — is_admin 与 ORM

- [x] 1.1 在 `app/user/models.py` 增加 `is_admin: Mapped[bool]`（默认 false）；不修改 `UserResponse` 暴露该字段
- [x] 1.2 编写 migration `003` 前半：`users.is_admin` 列；`alembic/env.py` 保持导入 `app.user.models`

## 2. TDD — 失败测试（红）

- [x] 2.1 扩展 `tests/conftest.py`：shop helpers（`create_shop_payload`、`register_and_open_shop`）与 `shop_owner` fixture（integration）
- [x] 2.2 按 `specs/catalog-shop/spec.md` 编写 `tests/catalog/test_create_shop.py`（201、重复开店 422、店名冲突 422、未认证 401）；**不编写** catalog 实现
- [x] 2.3 按 spec 编写 `tests/catalog/test_my_shop.py`（me 200/404、patch 200/404/422、closed）；**不编写** 实现
- [x] 2.4 按 spec 编写 `tests/catalog/test_public_shop.py`（公开 get active/closed 200、不存在 404）；**不编写** 实现
- [x] 2.5 编写 `tests/catalog/test_admin_seed.py`：migration 后断言 `114514yyut@qq.com` 存在且 `is_admin=true`；**不编写** 实现
- [x] 2.6 运行 `task db:up` 后 `task test`，确认 `tests/catalog/` 相关测试失败（红），记录预期失败原因

## 3. 迁移与 catalog 模型（绿 · 基础）

- [x] 3.1 实现 `app/catalog/models.py`（`Shop` ORM）；`alembic/env.py` 导入 `app.catalog.models`
- [x] 3.2 完成 migration `003`：`shops` 表 + seed 管理员（email `114514yyut@qq.com`；明文密码 `1919810810`；pwdlib hash 写入 `password_hash`）

## 4. catalog 域实现（绿 · 业务）

- [x] 4.1 实现 `app/catalog/schemas.py`、`repository.py`、`service.py`（开店、me、patch、公开 get；422/404 规则）
- [x] 4.2 实现 `app/catalog/deps.py`（`get_current_shop`）与 `router.py`；在 `app/main.py` 挂载路由

## 5. 本地验证与 CI

- [x] 5.1 运行 `task migrate` 后 `task ci` 确认本地全绿；手动 `curl` 注册 → 开店 → `/shops/me` → patch closed → 公开 GET
- [ ] 5.2 确认 GitHub Actions / 远程 CI 全绿（`workflow_dispatch` 或 PR）

## 6. 文档与 DoD

- [ ] 6.1 更新 `README.md`（店铺 API 演示）与 `docs/architecture.md`（`app/catalog/`、`shops` 表、003 migration）
- [ ] 6.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿、文档已更新；可执行 `/opsx:archive` 归档

> **Apply 约定**：严格 TDD，§2 完成前不得开始 §3–§4；每个 apply 会话建议只完成 1–2 个 task。

> **§2 红阶段预期失败（2026-07-14 验证）**：`tests/catalog/` 共 16 项，**13 失败、3 通过**（后者为路由未挂载时的**假绿**，实现后须仍绿）。
> - **12 项 HTTP**（create/my/public 需开店或断言 201/200/401/422）：catalog 路由未挂载（`app/main.py` 尚无 `/shops/*`）→ 响应 **404**，断言期望 201/200/401/422。
> - **3 项假绿**（`test_get_my_shop_returns_404_when_no_shop`、`test_patch_my_shop_returns_404_when_no_shop`、`test_get_public_shop_not_found_returns_404`）：因路由不存在返回 **404**，与业务层 404 断言重合，§4 实现后仍应通过。
> - **1 项**（`test_migration_seed_admin_exists`）：migration `003` 尚未 seed 管理员（Task 3.2）→ 查询 `114514yyut@qq.com` 为 **None**。
> - 既有 `tests/health/`、`tests/infra/`、`tests/user/` **27 项通过**。
