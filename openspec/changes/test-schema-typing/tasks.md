## 1. tests/support 基础设施

- [x] 1.1 新增 `tests/support/builders.py`：`build_register_request`、`build_login_request`、`build_shop_create`、`build_category_create`、`build_product_create`；迁移 `unique_email` / `unique_shop_name` / `unique_category_name`（或从 conftest re-export）
- [x] 1.2 新增 `tests/support/contexts.py`：`AuthContext`、`AdminAuthContext`、`ShopOwnerContext`（含嵌套 `auth`；`ShopOwnerContext.status_code` 指开店步骤）
- [x] 1.3 新增 `tests/support/results.py`：`RegisterResult`、`LoginResult`、`CategoryResult`（及需要的 `ShopResult`）；字段含 `status_code` 与 `body: XxxResponse | None`

## 2. conftest 重构

- [x] 2.1 重构 `register_user`、`login_user` 返回 Result dataclass；2xx 时用 `TokenResponse.model_validate`；移除 dict 返回
- [x] 2.2 重构 `create_category`（及拆出的 `create_shop` 若需要）返回 Result dataclass
- [x] 2.3 重构 fixture：`authenticated_user` → `AuthContext`，`admin_auth_headers` → `AdminAuthContext`，`shop_owner` → `ShopOwnerContext`；删除 `create_shop_payload` 与 `product_payload` fixture，改用 builders
- [x] 2.4 保留 `client`、`db_session`、env 配置与 engine reset fixture 行为不变

## 3. user integration 测试迁移

- [x] 3.1 迁移 `tests/user/test_register.py`：typed 断言；4 条中 2 条格式用例（password too short/long）加 `TODO(test-schema-unit-tests)`，最小改动
- [x] 3.2 迁移 `tests/user/test_login.py` 与 `tests/user/test_me.py`：使用 Context/Result 属性访问

## 4. catalog integration 测试迁移

- [ ] 4.1 迁移 `tests/catalog/test_create_shop.py`、`test_my_shop.py`、`test_public_shop.py`
- [ ] 4.2 迁移 `tests/catalog/test_admin_categories.py`、`test_categories_public.py`
- [ ] 4.3 迁移 `tests/catalog/test_create_product.py`（含 2 条格式 TODO）、`test_update_product.py`、`test_my_products.py`、`test_public_products.py`

## 5. 验证与 DoD

- [ ] 5.1 确认 `tests/infra/`、`tests/health/` 无因 conftest 删除符号而 broken import
- [ ] 5.2 运行 `devbox run -- task db:up`、`devbox run -- task migrate`、`devbox run -- task ci` 全绿
- [ ] 5.3 确认无 `app/*/schemas.py` 变更；grep 测试目录无新增 `result["json"]` / `shop_owner["headers"]` 模式（格式 TODO 用例除外）

> **Apply 约定**：建议顺序 §1 → §2 → §3 → §4 → §5；每个 apply 会话完成 1–2 个 task。本 change 为测试重构，**不**改业务实现；每完成一节可运行 `task test` 验证。

> **后续 change**：`test-schema-unit-tests` 将新增 schema 单测并删除 4 条格式边界 HTTP 用例。
