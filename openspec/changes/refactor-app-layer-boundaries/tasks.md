# refactor-app-layer-boundaries

> **Phase > Task**：Phase 是高于 `## N.` Task 组的迭代单元（见 `design.md`）。  
> Phase 内小步用 **Phase A Task X.X** / **Phase B Task X.X** 标注；Phase 闭环 = 该 Phase 下全部 Task 组勾选 + design Changelog + CI 绿。

## 0. 分支与准备

- [x] 0.1 从 `dev` 切分支 `refactor/app-layer-boundaries`
- [x] 0.2 通读 `proposal.md`、`design.md`、本文件 Phase A/B 范围

---

## Phase A — ordering：router 收编排 + service 返 schema

**DoD**：`app/ordering/router.py` 无 `ShopService` / `get_shop_service`；写路径 `OrderService` 公开方法返回 `OrderResponse` / `PaginatedOrders` / `BatchPayResponse`；ordering 相关 tests 绿。

## 1. OrderService 返回 schema（`_to_*` 收拢）

- [x] Phase A Task 1.1 合并 router `_to_response` 与 `OrderService._to_order_response`，统一为 service 层映射；router 删除 `_to_response`
- [x] Phase A Task 1.2 `OrderService` 写方法改为返回 schema（`create_order`、`pay_order`、`create_shipment`、`confirm_receipt`、`cancel_order`、`batch_pay_orders` 等）；router 直接 `return await service.*`

## 2. 跨域编排迁入 OrderService

- [x] Phase A Task 2.1 卖家建单：将 router 内 `catalog_service.get_my_shop` + `create_order_by_seller(shop.id, …)` 迁入 `OrderService.create_order_by_seller(owner_user_id, …)`；router 仅注入 `OrderService`
- [x] Phase A Task 2.2 店主发货：将 router 内 shop 归属校验迁入 `OrderService.create_shipment`（或 ordering deps + service 组合）；router 不再注入 catalog
- [x] Phase A Task 2.3 店主订单列表：将 `list_shop_orders` router 内 `get_my_shop` 迁入 `OrderService.list_shop_orders(owner_user_id, …)`
- [x] Phase A Task 2.4 `pay_order` / `cancel_order`：将 buyer 校验与 `cancel_reason` 分支迁入 service；router 只传 `user_id`

## 3. Router 清理与 Phase A 验证

- [ ] Phase A Task 3.1 清理 `app/ordering/router.py`：`rg` 确认无 `ShopService|get_shop_service|from app.catalog`；移除无用 import
- [ ] Phase A Task 3.2 `devbox run -- task db:up` → `migrate` → `redis:up` → `devbox run -- task ci`；更新 `design.md` Changelog（Phase A 完成摘要）

---

## Phase B — catalog：实体 service 拆分

**DoD**：`CategoryService` / `ProductService` / `ShopService` 分离；`deps` 分设 `get_*_service`；catalog router 按端点注入对应 service；ordering / engagement / support 的 catalog 依赖改为 narrow service；全量 CI 绿。

## 1. catalog 域内 service / deps / router 拆分

- [ ] Phase B Task 1.1 从现 `ShopService` 拆出 `CategoryService` + `get_category_service`；`/categories*` router 改用之
- [ ] Phase B Task 1.2 拆出 `ProductService` + `get_product_service`（含库存、可购/engagement 读、product ref 校验、media helper）；`/products*` router 改用之
- [ ] Phase B Task 1.3 收窄 `ShopService` 为店铺专用 + `get_shop_service`（仅 shop repo + media）；`/shops*` router 改用之

## 2. 跨域调用方 narrow 依赖

- [ ] Phase B Task 2.1 更新 `app/ordering/service.py` / `cart_service.py` / `deps.py`：catalog 依赖改为 `ProductService`（及必要的 `ShopService`），无上帝 `ShopService`
- [ ] Phase B Task 2.2 更新 `app/engagement/service.py` / `deps.py`：`ProductService.get_products_for_engagement`
- [ ] Phase B Task 2.3 更新 `app/support/service.py` / `deps.py`：`ShopService` + `ProductService`（或 shop 委托校验）替代单一上帝注入
- [ ] Phase B Task 2.4 删除或瘦身原 `app/catalog/service.py` 上帝类；修正全库 `from app.catalog.service import ShopService` 引用

## 3. Phase B 验证

- [ ] Phase B Task 3.1 跑 catalog / ordering / engagement / support 相关 tests；`devbox run -- task ci` 全绿
- [ ] Phase B Task 3.2 更新 `design.md` Changelog；准备 PR（scope: ordering + catalog + engagement + support）

---

## 4. 收尾（merge 后）

- [ ] 4.1 PR merge 到 `dev`；远程 CI 全绿
- [ ] 4.2 archive change；sync `refactor-regression` delta 至主 spec（若采用）；**不**在本 change sync 工程纪律全文（留给 `docs-app-layer-discipline`）
