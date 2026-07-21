## 0. 评审修复（buyer-orders 代码，先于 §1）

- [x] 0.1 `expire_if_needed` 成功释放后同步 ORM `status`/`cancel_reason`；`list_buyer_orders` / `list_shop_orders` 逐单懒释放
- [x] 0.2 扩展 `test_list_orders.py`：买家/店主列表路径过期后响应体为 `cancelled`/`expired` 且库存还原
- [x] 0.3 `app/ordering/router.py` 移除 `catalog.models.Shop`；`GET /shops/me/orders` 改经 `catalog.service.get_my_shop`

## 1. TDD — 失败测试（红）

- [x] 1.1 扩展 `tests/support/`：`create_order_by_seller` helper、禁用用户 seed（或 fixture）；**禁止** test 文件互 import
- [x] 1.2 编写 `tests/ordering/test_create_order_by_seller.py`（201、`initiated_by=seller`、买家 404、禁用 422、自购 403、**非本店商品 422**、closed 422、401、无店 404）；**不编写** 实现
- [ ] 1.3 编写 `tests/user/test_user_summary.py` 或 unit 覆盖 `get_user_summary`（200 摘要、404、422 禁用）；**不编写** 实现
- [ ] 1.4 扩展 `tests/ordering/test_list_orders.py`：买家建单→店主列表可见；卖家建单→买家列表可见；`initiated_by` 字段；列表路径懒释放（短 TTL）；**不编写** 实现
- [ ] 1.5 扩展 `tests/ordering/test_pay_order.py`：指定买家 pay 卖家发起的单→confirmed；店主 pay 卖家单→403
- [ ] 1.6 `devbox run -- task db:up` 后跑新增/扩展测试，确认失败（红）；在本文件备注预期失败原因

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§4。

## 2. 迁移与 user 域（绿 · 基础）

- [ ] 2.1 `app/user/schemas.py` 增加 `UserSummary`；`UserService.get_user_summary`（404/422）
- [ ] 2.2 `app/ordering/models.py` 增加 `initiated_by`；migration `006` 追加列并回填 `buyer`

## 3. ordering 域实现（绿 · 业务）

- [ ] 3.1 `OrderResponse` 等 schema 暴露 `initiated_by`；`SellerOrderCreate` 请求体；**同步更新** `router._to_response` 映射 `initiated_by`
- [ ] 3.2 重构 `OrderService`：抽取建单内核（含 `expected_shop_id` 校验）；`create_order_by_seller`；注入 `UserService`
- [ ] 3.3 `POST /shops/me/orders` 路由；`POST /orders` 写 `initiated_by=buyer`
- [x] 3.4 `list_buyer_orders` / `list_shop_orders` 列表路径逐单 `expire_if_needed`（§0.1 已完成）
- [ ] 3.5 静态检查：`app/ordering/` 无 `catalog.models` / `user.models` import；后续域改动顺手清类似小违规

## 4. 本地验证与 CI

- [ ] 4.1 `devbox run -- task migrate` 后 `devbox run -- task ci` 全绿；curl：卖家建单 → 买家 pay → 双列表可见
- [ ] 4.2 确认远程 CI 全绿（`workflow_dispatch` 或 PR）

## 5. 文档与 DoD

- [ ] 5.1 更新 `README.md`（`POST /shops/me/orders`、`initiated_by`、列表懒释放）
- [ ] 5.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿；可 `/opsx:archive`
