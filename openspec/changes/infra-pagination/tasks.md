## 1. Infra 分页模块（TDD）

- [x] 1.1 编写 `tests/infra/test_pagination.py`（Query 边界、`PaginationParams` 为 Pydantic model 非 tuple、`Paginated[TResponse]` 序列化；**不编写** `app/infra/pagination/` 实现）
- [x] 1.2 实现 `app/infra/pagination/`：`__init__.py`、`constants.py`、`schemas.py`（`Paginated[TResponse]`、`PaginationParams`）、`deps.py`（`get_pagination_params` 返回 `PaginationParams` + `Annotated` Query）；跑绿 1.1

## 2. Catalog 域迁移

- [ ] 2.1 `app/catalog/schemas.py`：`class PaginatedProducts(Paginated[ProductResponse])` thin subclass + OpenAPI title（Decision 8）；删除独立同形 `BaseModel`
- [ ] 2.2 `app/catalog/service.py`：删除 **catalog service 内** `_clamp_pagination` 及 `_DEFAULT_PAGE_LIMIT`/`_MAX_PAGE_LIMIT`（**勿删** ordering router 的同名函数）；`list_my_products` / `list_public_products` 回显入参 `limit`/`offset`
- [ ] 2.3 `app/catalog/router.py`：两列表端点改用 `Depends(get_pagination_params)`，以 `params.limit` / `params.offset` 传 service；移除内联 `Query`
- [ ] 2.4 跑绿 `tests/catalog/test_public_products.py`、`tests/catalog/test_my_products.py`

## 3. Ordering 域迁移（仅列表；半统一）

> **纪律**：本组 **禁止** 修改非列表 handler（create/get/pay/cancel/ship/batch-pay）的 `_to_response` 调用。

- [ ] 3.1 `app/ordering/schemas.py`：`class PaginatedOrders(Paginated[OrderResponse])` thin subclass + OpenAPI title
- [ ] 3.2 `app/ordering/repository.py`：`list_by_buyer` / `list_by_shop` 改用 `select(func.count()).select_from(Order).where(...)`（**单表**，不用 catalog subquery）；移除 `limit`/`offset` 默认值
- [ ] 3.3 `app/ordering/service.py`：`list_buyer_orders` / `list_shop_orders` 返回 `PaginatedOrders`（列表路径 ORM→DTO + 组装外壳）；**不**迁移其它 method 的 DTO 转换
- [ ] 3.4 `app/ordering/router.py`：删除 **ordering router 内** `_clamp_pagination` 与 `_DEFAULT_LIMIT`/`_MAX_LIMIT`（**勿删** catalog service 已删的函数）；两列表端点改用 infra Depends（`params.limit`/`params.offset`）并透传 service 返回值
- [ ] 3.5 跑绿 `tests/ordering/test_list_orders.py`

## 4. 文档与工程纪律

- [ ] 4.1 新增 `docs/decision/infra分页与列表数据流.md`（重构前后四端点对比、层职责、**半统一状态**、N+1 为既有债、follow-up）
- [ ] 4.2 更新 `docs/architecture.md`：infra 分页已实现（简短 + 链接 ADR）
- [ ] 4.3 新增 `.cursor/rules/pagination-discipline.mdc`（层职责；`PaginationParams` 非 tuple；**禁止** apply 时改动 ordering 非列表 `_to_response`）

## 5. 验证

- [ ] 5.1 `uv run ruff check .`
- [ ] 5.2 `devbox run -- task ci` 全绿

## Follow-up（本 change 不实现）

- [ ] — `ordering-dto-in-service`：非列表 `_to_response` 全面下沉 service；可选共享 `order_to_response` helper
- [ ] — `catalog-list-batch-categories`：消除 `_load_product_categories` N+1
- [ ] — `ordering-list-batch-items`：消除 `list_by_order_id` 逐单 N+1
