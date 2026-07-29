## Why

`ordering-buyer-orders` 已交付单笔立即购买路径，但缺少**购物车暂存**与**跨店结算**能力：用户无法长期收藏多店商品、按店分组浏览，也无法在一次结算后找回「这批待支付订单」并合并支付。架构文档 Phase 2 规划购物车归入 `ordering` 域；本 change 补齐买家购物车 → 结算 → 合并支付闭环，与现有 `POST /orders` 立即购买并行。

## What Changes

- 新增 **ordering 域购物车**：`cart_items` 表；`GET/POST/PATCH/DELETE /cart*`（需认证；不支持未登录购物车）
- **列表展示**：`GET /cart` 通过 **catalog.service** 批量 enrichment、按店铺分组；不可购项（下架/关店/不存在）进入 `invalid_items`；**不**使用跨域 ORM relationship
- **加购语义**：`POST /cart/items` 新增行；`PATCH /cart/items/{id}` 改数量；同一用户同一商品唯一（`UNIQUE(user_id, product_id)`）
- **部分结算**：`POST /cart/checkout` body `{ "cart_item_ids": [...] }`；按店 split 建单；未提交行保留在 cart
- **轻量结算分组**：`checkout_batches` 表（仅 `id`、`buyer_user_id`、`created_at`）；`orders.checkout_batch_id` 可空（立即购买为 NULL）；`GET /orders/checkout-batches/{id}` 供前端层级展示与「离开后再回来」找回同批待付
- **结算事务**：checkout **单 DB 事务**——创建 batch + N 个子订单（`awaiting_payment` + 库存预留 + 行快照）+ 删除对应 cart 行；任一失败全 rollback
- **锁价**：购物车展示 catalog 实时价；成交价以 checkout 建单时 `order_items` 快照为准
- **通用合并支付**：`POST /orders/batch-pay` `{ "order_ids": [...] }`——任意本人合法 `awaiting_payment` 且未过期子集（可跨 batch、可含立即购买单）；支付桩；**不要求**一次付清某 batch 全部子单
- 保留现有 **`POST /orders`** 立即购买及 **`POST /orders/{id}/pay`** 单笔支付
- 扩展 **pytest**：`tests/ordering/` 购物车与 batch-pay integration
- 更新 **docs/architecture.md**（购物车、checkout_batch、batch-pay）

## Non-goals

- 不实现未登录/匿名购物车及登录合并
- 不实现 `cart_items.selected` 字段（选中由前端提交 `cart_item_ids`）
- 不实现 checkout_batch 行项目、独立总价、独立状态机或独立 pay 接口（父级仅分组展示）
- 不实现 checkout 失败或订单取消后自动恢复 cart 行
- 不实现 GET /cart 自动清理失效行（仅展示 + 用户手动 DELETE）
- 不实现真实支付渠道、退款、运费、地址簿
- 不实现跨 checkout 的「父级部分金额支付」（仅对子 order 粒度 batch-pay）
- 不实现 checkout 多事务建单（非 MVP；失败补偿/saga 留后续）
- 不实现 `GET /orders/checkout-batches` 列表（仅按 id 查单 batch；不做 buyer 维度 batch 列表）
- 不修改 catalog / user 域对外 API 契约（仅调用既有 service）

## Capabilities

### New Capabilities

- `ordering-buyer-cart`：买家购物车 CRUD、按店分组列表与失效项、cart checkout（跨店单事务）、轻量 `checkout_batches`、通用 `POST /orders/batch-pay`（本 change 单 spec 覆盖全部验收场景）

### Modified Capabilities

- （无）batch-pay 与购物车验收统一写入 `ordering-buyer-cart/spec.md`，不 delta 既有 spec

## Impact

- **业务域**：`ordering`（cart、checkout_batch、batch-pay；扩展 `orders` 表）
- **跨域只读**：`catalog.service`（可购查询、列表 enrichment）；checkout 写路径复用既有 `reserve_stock` / `_create_order_core`
- **新增/修改**：`app/ordering/*`（cart router/service/repo、checkout_batch、batch-pay）、`alembic/versions/007_*.py`、`app/main.py`、`tests/ordering/`、`docs/architecture.md`
- **测试支持层**：`tests/support/helper/ordering.py`（cart/checkout/batch-pay 原子 helper）、`tests/support/db/ordering.py`（必要时 cart seed）、`tests/support/results.py`（Cart/CheckoutBatch 等 `*Result`）
- **API**：新增 `/cart*`、`/cart/checkout`、`/orders/checkout-batches/{id}`、`POST /orders/batch-pay`；保留 `/orders` 立即购买
- **分支**：基于 `dev` 的 `feature/ordering-buyer-cart`
