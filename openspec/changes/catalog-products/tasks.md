## 1. TDD — 失败测试（红）

- [ ] 1.1 扩展 `tests/conftest.py`：`admin_auth_headers`（seed 管理员登录）、`create_category` helper、`product_payload` fixture
- [ ] 1.2 编写 `tests/catalog/test_admin_categories.py`（POST 201/403/401/422 同级重名）；**不编写** 实现
- [ ] 1.3 编写 `tests/catalog/test_categories_public.py`（GET 扁平/空数组）；**不编写** 实现
- [ ] 1.4 编写 `tests/catalog/test_create_product.py`（POST 201、closed 422、无店 404、类目/primary 422）；**不编写** 实现
- [ ] 1.5 编写 `tests/catalog/test_my_products.py`（GET /shops/me/products 200/404、分页）；**不编写** 实现
- [ ] 1.6 编写 `tests/catalog/test_public_products.py`（GET 列表/详情、category_id 筛选、未上架/closed 404）；**不编写** 实现
- [ ] 1.7 编写 `tests/catalog/test_update_product.py`（PATCH 200、403 越权、closed 422、stock=0、is_published 下架）；**不编写** 实现
- [ ] 1.8 运行 `task db:up` 后 `task test`，确认 `tests/catalog/` 新增 product/category 相关测试失败（红），在 tasks 或 commit 消息中记录预期失败原因

## 2. 迁移与 ORM（绿 · 基础）

- [ ] 2.1 在 `app/catalog/models.py` 增加 `Category`、`Product`、`ProductCategory` ORM；`alembic/env.py` 已导入 catalog models
- [ ] 2.2 新增 migration `004`：`categories`、`products`、`product_categories`（**不** seed 类目）

## 3. user 域 — require_admin

- [ ] 3.1 在 `app/user/deps.py` 实现 `require_admin`（查库 `is_admin`；false→403，无用户/token 无效→401）

## 4. catalog 域实现（绿 · 业务）

- [ ] 4.1 扩展 `schemas.py`（Category*、ProductCreate/Update/Response、PaginatedProducts）；`repository.py`（类目/商品/关联 CRUD）
- [ ] 4.2 扩展 `service.py`（create_category、list_categories、create/update/list/get products；closed/403/422 规则；is_primary 校验）
- [ ] 4.3 扩展 `router.py`（注册顺序：`/shops/me/products` 先于 `/shops/{shop_id}`）；挂载 categories + products 路由（`POST /categories` 依赖 `require_admin`）

## 5. 本地验证与 CI

- [ ] 5.1 运行 `task migrate` 后 `task ci` 全绿；手动 curl：admin 建类目 → 商家上架 → 公开 GET
- [ ] 5.2 确认远程 CI 全绿（`workflow_dispatch` 或 PR）

## 6. 文档与 DoD

- [ ] 6.1 更新 `README.md`（类目/商品 API）与 `docs/architecture.md`（004 migration、products 表）
- [ ] 6.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿；可 `/opsx:archive`

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§4；§2 完成后做 §3（`require_admin`），再做 §4；每个 apply 会话建议只完成 1–2 个 task。

> **§1 红阶段预期失败**：`tests/catalog/` 新增 category/product 相关用例在路由与实现未挂载前，多数 HTTP 断言期望 201/200/401/403/422，实际响应 **404**；`GET /categories` 空数组等用例亦可能 404。`require_admin` 与 router 就绪（§3–§4）后，状态码应逐步符合 spec。
