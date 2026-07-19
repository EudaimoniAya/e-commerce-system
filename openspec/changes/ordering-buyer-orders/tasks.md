## 1. TDD — 失败测试（红）

- [ ] 1.1 扩展 `tests/support/`：订单相关 actions/seeds（如创建可购商品上下文、短 TTL 配置辅助）；**禁止** test 文件互 import；对齐四层架构
- [ ] 1.2 编写 `tests/ordering/test_create_order.py`（201 多行同店、跨店 422、超卖 4xx、未上架/closed 店、自购 403、401）；**不编写** 实现
- [ ] 1.3 编写 `tests/ordering/test_pay_order.py`（支付桩 200→confirmed、非买家 403、重复 pay 409、未认证 401、过期后 409 且库存还原）；**不编写** 实现
- [ ] 1.4 编写 `tests/ordering/test_shipments_and_receipt.py`（shipments 201、非店主 403、非 confirmed 409、未认证 401、confirm-receipt 200→completed 与 401）；**不编写** 实现
- [ ] 1.5 编写 `tests/ordering/test_cancel_order.py`（买家/卖家取消与库存加回、completed 409、未认证 401）；**不编写** 实现
- [ ] 1.6 编写 `tests/ordering/test_list_orders.py`（买家列表、店主 `/shops/me/orders`、无关用户 GET 404、未认证 401、读单触发懒释放）；**不编写** 实现
- [ ] 1.7 `devbox run -- task db:up` 后跑新增 ordering 测试，确认失败（红）；在 commit 消息或本文件备注预期失败原因

## 2. 配置与迁移 / ORM（绿 · 基础）

- [ ] 2.1 `Settings` / `.env.example` 增加 `ORDER_RESERVATION_TTL_SECONDS`（默认 86400）
- [ ] 2.2 新增 `app/ordering/models.py`（Order、OrderItem）；`alembic/env.py` 导入 ordering models
- [ ] 2.3 新增 migration `005`：`orders`、`order_items` 及设计中的索引

## 3. catalog 域 — 可购查询与库存预留/释放

- [ ] 3.1 扩展 `app/catalog/schemas.py`：`PurchasableProduct`（或等价）DTO
- [ ] 3.2 扩展 `repository` + `ShopService`（或拆出库存方法）：批量可购查询、`reserve_stock`（条件更新）、`release_stock`；必要时补 `tests/unit` 或 catalog 侧最小覆盖

## 4. ordering 域实现（绿 · 业务）

- [ ] 4.1 `app/ordering/schemas.py` + `repository.py`（订单/行 CRUD、条件更新 status）
- [ ] 4.2 `app/ordering/service.py`：创建（校验同店/自购/可购 + reserve + 快照）、懒释放 `expire_if_needed`、pay 桩、shipments、confirm-receipt、cancel、列表查询
- [ ] 4.3 `app/ordering/router.py` + `deps.py`；`main.py` 挂载；路由顺序注意 `/shops/me/orders` 与现有 shop 路由共存

## 5. 本地验证与 CI

- [ ] 5.1 `devbox run -- task migrate` 后 `devbox run -- task ci` 全绿；手动 curl：下单 → pay → shipments → confirm-receipt；短 TTL 过期懒释放
- [ ] 5.2 确认远程 CI 全绿（`workflow_dispatch` 或 PR）

## 6. 文档与 DoD

- [ ] 6.1 更新 `README.md`（订单 API）与 `docs/architecture.md`（ordering 域、状态机、预留 TTL、005 migration）
- [ ] 6.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿；可 `/opsx:archive`

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§4；§2 完成后做 §3（catalog 库存接口），再做 §4；每个 apply 会话建议只完成 1–2 个 task。

> **§1 红阶段预期失败**：`tests/ordering/` 在路由未挂载前多为 **404**；断言期望 201/200/401/403/409/422 等业务码。
