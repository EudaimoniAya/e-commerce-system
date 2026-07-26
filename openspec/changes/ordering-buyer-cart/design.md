## Context

`ordering-buyer-orders` 与 `ordering-seller-orders` 已交付：`POST /orders` 立即购买（单店）、`POST /orders/{id}/pay` 单笔支付桩、库存预留/懒释放、FSM 均已就绪。Explore 已收敛购物车需求：

- 购物车为 **长期暂存**（多店、实时价展示、不占库存、不建单）
- **结算**（`POST /cart/checkout`）在 **单 DB 事务** 内按店 split → 创建轻量 `checkout_batch` + N 个子 `orders`（`awaiting_payment`）→ 删除对应 `cart_items`
- **轻量 batch** 仅服务前端分组展示（「离开后再回来找同批待付」）；支付走 **通用** `POST /orders/batch-pay`，不绑定购物车
- 跨域纪律不变：ordering → `catalog.service` + schemas；禁止 import `catalog.models` / repository

## Goals / Non-Goals

**Goals:**

- 可演示闭环：加购 → 按店列表 → 部分 checkout → 确认页（锁价快照）→ batch-pay（可分批）→ 既有发货/收货路径
- `cart_items`、`checkout_batches` 表；`orders.checkout_batch_id` 可空
- 复用 `OrderService._create_order_core` 按店建单；checkout 编排与 cart 删行同事务
- TDD + 四层测试；422/409 与既有 ordering 约定一致

**Non-Goals:**

- 未登录 cart、selected 字段、跨域 ORM relationship、父级行项目/总价/独立 pay
- checkout 失败或 cancel 后自动恢复 cart；GET 自动清理失效行
- checkout 多事务建单、真实支付、运费/地址
- `GET /checkout-batches` 列表（无 buyer 维度 batch 列表 API；不做 `ix_checkout_batches_buyer_user_id`）

## Decisions

### 1. 域内模块划分（ordering）

```text
app/ordering/
  cart_router.py          # /cart*、/checkout-batches/{id}（或合入 router.py 前缀分组）
  cart_service.py         # CartService：CRUD + list enrichment + checkout 编排入口
  cart_repository.py
  checkout_batch_repository.py
  service.py              # OrderService：_create_order_core、batch_pay_orders
  models.py               # + CartItem、CheckoutBatch；Order.checkout_batch_id
```

cart 与 order 同属 ordering 域；**CartItem 不** relationship 到 catalog.Product。

### 2. 数据模型（ordering 域）

#### `cart_items`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `user_id` | CHAR(36) | FK 语义 → users.id |
| `product_id` | CHAR(36) | 仅存 ID |
| `qty` | INT | ≥ 1 |
| `created_at` / `updated_at` | DATETIME | |

约束：`UNIQUE(user_id, product_id)`。索引：`ix_cart_items_user_id`。

#### `checkout_batches`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `buyer_user_id` | CHAR(36) | FK 语义 → users.id |
| `created_at` | DATETIME | |

**无** status、total、行表。展示态由子 orders 聚合推导（见 Decision 6）。

#### `orders`（扩展）

| 列 | 类型 | 说明 |
|----|------|------|
| `checkout_batch_id` | CHAR(36) NULL | FK → checkout_batches.id；`POST /orders` 立即购买为 NULL |

索引：`ix_orders_checkout_batch_id`（可空）。

migration：`007_ordering_cart.py`（当前 head 为 `006_ordering_initiated_by`；名以 alembic 生成为准）。

### 3. GET /cart：catalog enrichment，无 relationship

流程：

1. `CartRepository.list_by_user_id(user_id)`
2. 收集全部 `product_id` → **一次** `catalog.service.get_purchasable_products(ids)` 批量查询（既有接口接受 `list[str]`，**避免 N+1**）
3. 可购且 `is_published` + shop `active` → 归入 `shops[]`（按 `shop_id` 分组；店名来自扩展后的 `PurchasableProduct.shop_name` 或等价字段）
4. 其余 → `invalid_items[]`（含 `reason`：`not_found` | `product_unpublished` | `shop_closed`）
5. 展示 `unit_price` 为 catalog **实时价**（非快照）

空 cart 响应形状：`{ "shops": [], "invalid_items": [] }`。

跨域调用：`ShopService.get_purchasable_products` → `list[PurchasableProduct]`（当前 DTO **无** `shop_name`；apply 开始前按 task 6.1 最小扩展）。

### 4. Cart CRUD 语义

| 方法 | 行为 |
|------|------|
| `POST /cart/items` | `{ product_id, qty }`；`product_id` 在 catalog 不存在 → **422**；若 `(user_id, product_id)` 已存在 → **422**（提示用 PATCH 改数量） |
| `PATCH /cart/items/{id}` | 改 `qty`（≥ 1）；须属当前用户；id 不存在 → **404** |
| `DELETE /cart/items/{id}` | 删单行；须属当前用户；id 不存在 → **404** |
| 认证 | 全部需 JWT；未登录 → 401 |

不加 `selected`；批量删失效项由用户多次 DELETE 或后续 enhancement。

### 5. Checkout 编排归属与单事务

**编排入口**：`CartService.checkout()` 为 **唯一** checkout 入口；**唯一** 在该方法末尾调用 `session.commit()`（或失败时 rollback）。

**OrderService** 只提供可嵌入的建单内核，**不**拥有 checkout 事务边界。

```text
CartService.checkout(cart_item_ids)
  ├─ 1. 加载 cart items；缺失/不属用户 → 422
  ├─ 2. get_purchasable_products 批量校验
  ├─ 3. 按 shop_id 分组
  ├─ 4. INSERT checkout_batch
  ├─ 5. for each shop:
  │       OrderService._create_order_core(..., commit=False, checkout_batch_id=...)
  ├─ 6. DELETE 对应 cart_items
  └─ 7. session.commit()          ← 仅此处一次 commit

POST /orders → OrderService.create_order
  └─ _create_order_core(..., commit=True)   ← 立即购买保持原行为
```

**`_create_order_core` refactor（apply task 3.1，最小侵入）**：

- 新增参数 `commit: bool = True`、`checkout_batch_id: uuid.UUID | None = None`
- `commit=True`：末尾 `commit` + `refresh`（与现网 `POST /orders` 行为一致）
- `commit=False`：仅 `flush`；由 `CartService.checkout` 统一 `commit`/`rollback`
- refactor 后 **须保证** `tests/ordering/test_create_order.py` 与卖家建单测试仍全绿（重构不改变外部行为）

**锁价**：步骤 5 写入的 `order_items.unit_price` 即为确认页基准；之后 catalog 变价不影响这些 orders。

任一 shop 建单失败（422/403）→ **整单 rollback**，cart 不变。

### 6. GET /checkout-batches/{id}

- 仅买家本人；否则 404
- 加载 batch + `orders WHERE checkout_batch_id=?`
- 对每个 order：`expire_if_needed`；加载 items
- 响应聚合：`shops[]`（每店嵌 order + items）、`paid_total`、`remaining_total`（仅计 `awaiting_payment` 子单）、派生 `status`（**读时计算，不落库**）

**派生 status 全集（展示用）**：

| 子单状态组合 | 派生 status |
|--------------|-------------|
| 全部 `awaiting_payment` | `pending_payment` |
| 有 `confirmed` 且仍有 `awaiting_payment` | `partially_paid` |
| 全部 `confirmed` | `completed` |
| 全部终态（`confirmed`/`cancelled`/`completed`），无 awaiting | `closed` |
| 混合 `confirmed` + `cancelled`（含过期），无 awaiting | `closed` 或 `partially_paid`（响应须含各子单真实 status；`remaining_total` 仅计 awaiting） |

不引入 batch 专用 pay 端点；不做 batch 列表 API。

### 7. POST /orders/batch-pay（通用、宽松）

请求：`{ "order_ids": ["...", ...] }`（非空；空数组 → **422**）。

规则：

- 全部须存在且 `buyer_user_id` = 当前用户；否则 **404** / **403**
- **先**对全部 id 执行 `expire_if_needed`
- **再**校验全部为 `awaiting_payment`；任一非 awaiting 或已过期 → **409**，**零确认**（全有或全无，单事务）
- **不要求**同一 `checkout_batch_id`；可混合立即购买单与不同 batch 子单
- **不要求**付清某 batch 全部子单；`order_ids` 可为任意合法子集
- 同一 DB 事务内逐个条件更新 → `confirmed`；任一条失败 → rollback + **409**

支付桩语义与单笔 `pay_order` 一致；不二次扣库存。

### 8. 与立即购买共存

- `POST /orders`：不变；`checkout_batch_id = NULL`
- `POST /orders/{id}/pay`：不变
- 购物车路径：`cart → checkout → batch-pay`（或单笔 pay 子单）

### 9. HTTP 422 vs 409

沿用 ordering-buyer-orders 约定：

- checkout / cart 写入业务约束（库存、不可购、空 body、商品不存在、cart item 不属于用户）→ **422**
- batch-pay / pay 对已存在订单的非法状态 → **409**
- 自购 → **403**；cart item 不存在或不属用户 → **404**（PATCH/DELETE by id）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| `_create_order_core` 内置 commit 破坏 checkout 原子性 | task 3.1：`commit: bool = True` 参数；checkout 传 `False` |
| cart **实时价**与 checkout **快照价**不一致（用户在 cart 看到 A，结算时变为 B） | 产品预期：确认页只展示 checkout 响应 order 快照；非 bug |
| 部分 batch-pay 后其余子单过期 | 懒释放；GET batch 展示 remaining 与各子单 status |
| 用户混选 unrelated 待付单一次 batch-pay | 允许（宽松 batch-pay）；前端 UX 自行约束 |
| invalid cart 行堆积 | 展示 + 手动 DELETE；不自动清理 |
| batch 内部分子单 cancel 后展示复杂 | 派生 status 规则见 Decision 6；响应逐单带 status |

## Migration Plan

1. `alembic upgrade head` 新增 `cart_items`、`checkout_batches`、`orders.checkout_batch_id`
2. 部署 API；既有 orders 不受影响（`checkout_batch_id` NULL）
3. 回滚：downgrade migration；无数据迁移回填

## Open Questions

- **apply 开始前**：确认 `PurchasableProduct` 是否扩展 `shop_name`（当前仅有 `shop_id`）；见 task 6.1，须在 task 4.2 前定案。
