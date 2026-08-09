# refactor-app-layer-boundaries

> **Phase > Task**：Phase 是高于 `## N.` Task 组的迭代单元（见 `design.md`）。  
> Phase 内小步用 **Phase A / Phase B / Phase C Task X.X** 标注；Phase 闭环 = 该 Phase 下全部 Task 组勾选 + design Changelog + CI 绿。

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

- [x] Phase A Task 3.1 清理 `app/ordering/router.py`：`rg` 确认无 `ShopService|get_shop_service|from app.catalog`；移除无用 import
- [x] Phase A Task 3.2 `devbox run -- task db:up` → `migrate` → `redis:up` → `devbox run -- task ci`；更新 `design.md` Changelog（Phase A 完成摘要）

---

## Phase B — deps 规范化：current-object deps 本域独用、绝不建 schema

**核心原理**：跨域只走 service 接口 + schema；deps 是本域私有装配——**current-object deps 绝不跨域、绝不建 schema**（schema 由 service 产出）；service deps 是唯一允许的跨域接线（各域 service 依赖在 deps 汇聚）。理由：current-object deps 一旦跨域（如 support 用 catalog `get_current_shop`），deps 被当域公共面，诱发 deps 调 service 私有 `_to_*` 建 schema（`get_current_user`、`get_order_for_buyer_or_shop_response`），在 service 边界外绕出 deps 交互网（破窗/架构侵蚀）。规范全文留给 `docs-app-layer-discipline`。

**DoD**：`get_order_for_buyer_or_shop_response` 与 `get_current_user` 删除，读路径 schema 由 service 公开方法产出；support 店主路径不再 `Depends(get_current_shop)`；`app/*/deps.py` 不再 import service 私有映射函数；相关 tests 全绿。

## 1. ordering：读路径 schema 收进 service

- [x] Phase B Task 1.1 `OrderService` 增加公开方法 `get_order_response(order_id, user_id)`（fetch → 404 → 懒释放 → buyer/店主鉴权 → 私有 `_to_order_response`）；写路径内部仍用 `_to_order_response`
- [x] Phase B Task 1.2 删除 deps 内 `get_order_for_buyer_or_shop_response` 与 `_to_order_response` import；`get_order` router 改用 `get_current_user_id` + `service.get_order_response(order_id, user_id)`（`get_order_for_buyer_or_shop` 保留——cancel_order 写路径仍需，合法 current-object deps）

## 2. user：读路径 schema 收进 service

- [x] Phase B Task 2.1 `UserService` 增加公开方法 `get_user_response(user_id)`（fetch → 404 → 解析 avatar → 私有 `_to_user_response`）；`update_profile` 复用 avatar/映射 helper
- [x] Phase B Task 2.2 删除 `get_current_user` deps 与 `_to_user_response` / `_resolve_avatar_url` import；`GET /users/me` 改用 `get_current_user_id` + `service.get_user_response(user_id)`

## 3. catalog/support：消除跨域 current-object deps

- [x] Phase B Task 3.1 support 店主路径（`/support/inbox*`）不再 `Depends(get_current_shop)`；改注入 `user_id` + `SupportService`，经已注入 `ShopService.get_my_shop(user_id)` 解析本店（404 语义一致）
- [x] Phase B Task 3.2 移除 support router 的 `from app.catalog.deps import get_current_shop` 与 `from app.catalog.models import Shop`；`get_current_shop` 退回 catalog 域内私有（仅 catalog router 消费）；support / catalog 相关 tests 全绿

## 4. 验证与留档

- [x] Phase B Task 4.1 `rg 'from app.(ordering|user).service import _' app/*/deps.py` 无命中；`rg 'Depends\(get_current_shop\)' app/support/` 无命中；`devbox run -- task ci` 全绿；design.md Changelog 追加 Phase B 摘要

---

## Phase C — catalog：上帝 service 拆分（反模式 ④：上帝 service → 上帝 deps）

**核心原理**：单一上帝 `ShopService` 迫使 `get_shop_service()` 一次注入三 repo + `MediaService`——service 越界导致 deps 上帝化；跨域调用方（ordering / engagement / support）被迫依赖整个上帝类。拆为按实体 service + 按端点 deps，跨域收窄为 narrow 入口。

**DoD**：`CategoryService` / `ProductService` / `ShopService` 分离；`deps` 分设 `get_*_service`；catalog router 按端点注入对应 service；ordering / engagement / support 的 catalog 依赖改为 narrow service；全量 CI 绿。

## 1. catalog 域内 service / deps / router 拆分

- [x] Phase C Task 1.1 从现 `ShopService` 拆出 `CategoryService` + `get_category_service`；`/categories*` router 改用之
- [x] Phase C Task 1.2 拆出 `ProductService` + `get_product_service`（含库存、可购/engagement 读、product ref 校验、media helper）；`/products*` router 改用之
- [x] Phase C Task 1.3 收窄 `ShopService` 为店铺专用 + `get_shop_service`（仅 shop repo + media）；`/shops*` router 改用之

## 2. 跨域调用方 narrow 依赖

- [x] Phase C Task 2.1 更新 `app/ordering/service.py` / `cart_service.py` / `deps.py`：catalog 依赖改为 `ProductService`（及必要的 `ShopService`），无上帝 `ShopService`
- [x] Phase C Task 2.2 更新 `app/engagement/service.py` / `deps.py`：`ProductService.get_products_for_engagement`
- [x] Phase C Task 2.3 更新 `app/support/service.py` / `deps.py`：`ShopService` + `ProductService`（或 shop 委托校验）替代单一上帝注入
- [x] Phase C Task 2.4 删除或瘦身原 `app/catalog/service.py` 上帝类；修正全库 `from app.catalog.service import ShopService` 引用

## 3. Phase C 验证

- [x] Phase C Task 3.1 跑 catalog / ordering / engagement / support 相关 tests；`devbox run -- task ci` 全绿
- [x] Phase C Task 3.2 更新 `design.md` Changelog（Phase C 完成摘要 + 踩坑记录）

---

## Phase D — 跨域两步收编（反模式③ 精确定义）

**核心原理**：同域 current-object deps（`get_current_shop`、`get_order_for_buyer_or_shop` 等）是合法 FastAPI 惯用法——deps 解析本域请求上下文（含鉴权），保留。真正的反模式是**跨域两步调用**：Phase B 禁跨域 deps 后，跨域上下文靠 router 两步串联（support `shop_id = await service.get_current_shop_id(user_id)` → `service.list_inbox(shop_id, ...)`）。跨域上下文必须由 service 业务方法自解析、一步完成；schema 由 service 产出。

**DoD**：support 店主路径不再两步调用（`get_current_shop_id` 私有化）；cart checkout-batch 编排 + CRUD schema 收进 service（`_to_cart_item_response` 从 router 消失、无 `order_service._item_repo` 私有访问）；同域 deps（`get_current_shop` / `get_order_*`）与纯鉴权 gate 不动；全量 CI 绿。

## 1. support：跨域两步收编

- [ ] Phase D Task 1.1 `SupportService.list_inbox(user_id, ...)` / `get_inbox_conversation(user_id, conversation_id)` / `list_inbox_messages(user_id, ...)` / `send_shop_message(user_id, conversation_id, body)` 内部经 `_get_current_shop_id` 自解析本店
- [ ] Phase D Task 1.2 `get_current_shop_id` 公开 → 私有 `_get_current_shop_id`；support router 4 店主端点删两步、一步调用

## 2. cart：checkout-batch 编排收编

- [ ] Phase D Task 2.1 OrderService 暴露 `list_orders_by_checkout_batch(batch_id)`（含懒释放 + items；方案 A）；新增 `CartService.get_checkout_batch(batch_id, user_id)`（fetch/404/子订单/聚合/派生状态/build schema 全收编）
- [ ] Phase D Task 2.2 `_derive_batch_status` 迁入 service；cart_router checkout-batch 端点一行化；移除 `order_service._item_repo` 私有访问

## 3. cart：CRUD schema 收编

- [ ] Phase D Task 3.1 `_to_cart_item_response` 迁入 CartService；`add_item` 返回 `(CartItemResponse, created)`、`update_qty` 返回 `CartItemResponse`；删 router 映射函数

## 4. Phase D 验证

- [ ] Phase D Task 4.1 跑 support / cart / ordering 相关 tests；`devbox run -- task ci` 全绿
- [ ] Phase D Task 4.2 更新 `design.md` Changelog（Phase D 完成摘要）

---

## 收尾（所有 Phase 完成后，merge 后执行）

> 独立于任何 Phase 的 change 级收尾；后续新增 Phase（D/E…）插在 Phase C 之后、本节之前。

- [ ] 5.1 PR merge 到 `dev`；远程 CI 全绿
- [ ] 5.2 archive change；sync `refactor-regression` delta 至主 spec（若采用）；**不**在本 change sync 工程纪律全文（留给 `docs-app-layer-discipline`）
