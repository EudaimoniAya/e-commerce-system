## 1. TDD — 失败测试（红）

- [x] 1.1 扩展 `tests/support/`（遵循 test-architecture 四层；禁止 test 文件互 import）：
  - `helper/ordering.py` 原子 HTTP helper（返回 `*Result`，不 assert 成功）：`add_cart_item`、`patch_cart_item`、`delete_cart_item`、`get_cart`、`checkout_cart`、`get_checkout_batch`、`batch_pay_orders`
  - `db/ordering.py`：必要时 `seed_cart_item`（Case Arrange 直写 DB）
  - `results.py`：CartItemResult、CartListResult、CheckoutResult、CheckoutBatchResult、BatchPayResult 等
  - 复用既有 `arrange_purchasable_product` / 多店 seed 模式编排跨店 cart 场景
- [x] 1.2 编写 `tests/ordering/test_cart_crud.py`（POST/PATCH/DELETE、商品不存在 422、重复加购 422、cart_item 不存在 404、401）；不编写实现
- [x] 1.3 编写 `tests/ordering/test_cart_list.py`（GET 空 cart、按店分组、invalid_items、实时价、不自动删失效行）；不编写实现
- [x] 1.4 编写 `tests/ordering/test_cart_checkout.py`（跨店 201、部分结算留 cart、cart_item_ids 空 422、失败 422 cart 不变、锁价、自购 403、单事务）；不编写实现
- [x] 1.5 编写 `tests/ordering/test_checkout_batch.py`（GET batch 层级、paid/remaining、cancelled 混合、非本人 404、懒释放）；不编写实现
- [x] 1.6 编写 `tests/ordering/test_batch_pay.py`（多单成功、order_ids 空 422、跨 batch+立即购买、子集支付、部分过期零确认 409、非法 409、全有或全无、401）；不编写实现
- [x] 1.7 `devbox run -- task db:up` 后跑新增 ordering cart 测试，确认失败（红）

### 1a. 测试基础设施增强（红阶段内）

- [x] 1a.1 新增 `second_shop_owner` fixture 至 `tests/conftest.py`（与 `shop_owner` 独立，用于跨店场景）
- [x] 1a.2 重写 `test_batch_pay_subset`：两个 checkout batch（均跨店 → 各 2 orders），batch-pay 每 batch 各 1 单，assert 付过的 confirmed、未付的仍 awaiting_payment
- [x] 1a.3 增强 `test_batch_pay_cross_batch_and_immediate`：2 个不同 batch 子单 + 1 个立即购买单；batch-pay 混合 batch1 子单 + 立即购买单；assert batch2 子单未被付
- [x] 1a.4 跑测试确认 1a.1–1a.3 改动后既有测试无回归，新增测试仍红

> **后续**：`second_shop_owner` fixture 将在独立 refactor change 中推广至全项目跨店测试，替换 `register_and_open_shop`。

## 2. 迁移与 ORM（绿 · 基础）

- [x] 2.1 扩展 `app/ordering/models.py`：`CartItem`、`CheckoutBatch`；`Order.checkout_batch_id`；`alembic/env.py` 导入
- [x] 2.2 新增 migration `007`：`cart_items`、`checkout_batches`、`orders.checkout_batch_id` 及索引

## 3. OrderService refactor（checkout 原子性）

- [x] 3.1 为 `_create_order_core` 增加 `commit: bool = True`、`checkout_batch_id` 参数；`commit=False` 时仅 flush；**确保** `tests/ordering/test_create_order.py` 与卖家建单测试 refactor 后仍全绿（外部行为不变）
- [x] 3.2 扩展 `Order` repository：按 `checkout_batch_id` 查询；batch-pay 批量条件更新 status

## 4. Cart 实现（绿）

- [x] 4.0a 扩展 `PurchasableProduct.shop_name` + `get_purchasable_products`（catalog 域；禁止 ordering 跨域 ORM）
- [x] 4.1 `cart_repository.py` + cart 相关 schemas（或合入 schemas.py）
- [x] 4.2 `CartService`：CRUD + `GET /cart` enrichment（批量 `get_purchasable_products`、按店分组、invalid_items）
- [x] 4.3 `cart_router.py`（或 router 前缀）；`main.py` 挂载 `/cart*`

## 5. Checkout batch 与 batch-pay（绿）

- [x] 5.1 `checkout_batch_repository.py` + **`CartService.checkout` 唯一编排入口**（单事务：batch + N×`_create_order_core(commit=False)` + 删 cart；唯一 commit）
- [x] 5.2 `GET /orders/checkout-batches/{id}` router + 聚合响应（paid_total、remaining_total、派生 status、shops）
- [x] 5.3 `OrderService.batch_pay_orders` + `POST /orders/batch-pay` router

## 6. 本地验证与 CI

- [x] 6.1 `devbox run -- task migrate` 后 `devbox run -- task ci` 全绿；curl 烟雾：加购 → checkout → batch-pay（`scripts/ordering_cart_curl_smoke.sh`）
- [x] 6.2 确认远程 CI 全绿（workflow_dispatch [run #30223329794](https://github.com/EudaimoniAya/e-commerce-system/actions/runs/30223329794) success）

## 7. 文档与 DoD

- [x] 7.1 更新 `docs/architecture.md`（cart、checkout_batch、batch-pay、007 migration）
- [x] 7.2 确认 DoD：本地 `task ci` 全绿、远程 CI 全绿（已由 §6 覆盖）；可 `/opsx:archive`

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§5；§3 refactor 须在 §5.1 checkout 前完成；task 4.0a 须在 4.2 前完成；每个 apply 会话建议只完成 1–2 个 task。
