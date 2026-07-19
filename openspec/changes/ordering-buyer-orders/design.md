## Context

`user` 与 `catalog`（店铺 / 类目 / 商品）已交付；尚无 `app/ordering/`。架构文档原写极简三态（`pending → confirmed → completed`）且「创建即扣库存进 confirmed」；Explore 已收敛为更贴近演示闭环的状态机与**发起即预留**，支付用桩、物流后置。

本 change 只做**买家发起**路径；卖家开单留给后续 change。跨域纪律：ordering → `catalog.service` + schemas，禁止 import `catalog.models` / repository。

## Goals / Non-Goals

**Goals:**

- 可演示闭环：下单（预留）→ 支付桩 → 发货（shipments）→ 确认收货
- FSM + 规则表驱动非法迁移（409）；超时并入 `cancelled` + `cancel_reason=expired`
- 库存：创建条件扣减；取消/超时条件释放（防双加回）；仅懒释放
- catalog 暴露预留/释放 service；TDD + 四层测试架构

**Non-Goals:**

- 卖家发起、真支付、退货、物流子状态、Redis/MQ、周期扫描释放、购物车

## Decisions

### 0. HTTP 422 vs 409（全项目约定）

业务 4xx 按「失败挂在谁身上」二分（非 RFC 本体论，而是本仓库评审/客户端稳定约定；与 user/catalog 既有 422 用法对齐）：

| 码 | 含义 | ordering 例 |
|----|------|-------------|
| **422** | 要建/要写入的内容形态过了，相对业务语义或外部约束不成立 | 跨店、库存不足、未上架、店非 active；以及 catalog 侧店名占用、closed 禁写等 |
| **409** | 资源已存在，针对它的动作与当前生命周期阶段不合 | 非法状态迁移、重复 pay、终态再 cancel、过期后再 pay |

口诀：**422 = 建不成/按规则写不成；409 = 这份已存在资源拒收该操作。**  
并发超卖与单人买超走同一条件更新失败路径，统一 **422**，不拆码。401/403 仍专管认证/授权。

### 1. 状态机（FSM）

```text
awaiting_payment ──pay──▶ confirmed ──shipments──▶ shipped ──confirm-receipt──▶ completed
       │                      │                      │
       └──────── cancel / lazy-expire ───────────────┘
                         ▼
                    cancelled
```

| 状态 | 含义 |
|------|------|
| `awaiting_payment` | 已建单并预留库存，待支付桩 |
| `confirmed` | 已付（桩），可发货 |
| `shipped` | 卖家已创建 shipments（标发货） |
| `completed` | 买家确认收货；**禁止 cancel** |
| `cancelled` | 终态；含主动取消与超时 |

`cancel_reason`（字符串枚举，建议）：`buyer_cancelled` | `seller_cancelled` | `expired`。

非法迁移（含对 `completed`/`cancelled` 再操作）→ **409**。

### 2. 数据模型（ordering 域）

#### `orders`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `buyer_user_id` | CHAR(36) | FK 语义 → users.id；**不**声明跨域 relationship |
| `shop_id` | CHAR(36) | FK 语义 → shops.id |
| `status` | VARCHAR(32) | 见上表 |
| `cancel_reason` | VARCHAR(32) | 可空；仅 cancelled 时有值 |
| `total_amount` | DECIMAL(12,2) | Σ unit_price × qty（快照） |
| `expires_at` | DATETIME | 仅对 awaiting_payment 有意义 |
| `note` | VARCHAR(512) | 可空；shipments 可选写入或订单级备注（初版 shipments note 可落此列或忽略持久化——**推荐**：`orders.seller_note` 可空，shipments 时写入） |
| `created_at` / `updated_at` | DATETIME | |

索引：`ix_orders_buyer_user_id`、`ix_orders_shop_id`、`ix_orders_status`、`ix_orders_expires_at`。

#### `order_items`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `order_id` | CHAR(36) FK → orders.id | |
| `product_id` | CHAR(36) | 快照关联；不跨域 relationship |
| `product_name` | VARCHAR(128) | 创建时快照 |
| `unit_price` | DECIMAL(10,2) | 创建时快照 |
| `qty` | INT | > 0 |

- **1 订单 = 1 店 + 多行**；创建时校验所有 `product_id` 同属该 `shop_id`
- migration：`005_ordering_orders.py`（名以 alembic 生成为准）

### 3. 库存预留（catalog service）

**模型**：`products.stock` 单字段；创建订单时扣减 = 预留；取消/超时加回。

catalog 新增（命名可微调，语义固定）：

| 方法 | 行为 |
|------|------|
| `get_purchasable_products(product_ids) → list[PurchasableProduct]` | 返回 id、shop_id、name、price、stock、owner_user_id（或等价字段）；过滤/标注不可购 |
| `reserve_stock(items: list[{product_id, qty}])` | 同一事务内对每行 `UPDATE ... SET stock=stock-qty WHERE id=? AND stock>=qty`；任一行失败 → 抛错，整单不建 |
| `release_stock(items: list[{product_id, qty}])` | 加回库存（仅由 ordering 在「首次成功终态化取消/过期」后调用） |

ordering **不得** import catalog ORM。预留与建单应在**同一 DB session/事务**中完成（ordering service 编排：先校验 → reserve → insert order；失败回滚）。

### 4. 可下单规则

- 商品 `is_published=true` 且店铺 `status=active`；否则 → **422**
- 所有行同店；`qty >= 1`；库存条件更新成功；跨店或库存不足 → **422**
- **`buyer_user_id != shop.owner_user_id`** → 否则 **403**（禁自购）
- 未认证 → 401

### 5. 超时与懒释放

- `expires_at = created_at + ORDER_RESERVATION_TTL_SECONDS`（Settings；默认 `86400`；测试可覆盖为短 TTL）
- **仅懒释放**：在 `pay`、创建订单前/中、`GET /orders/{id}`（及列表若方便）路径调用 `ensure_not_expired(order)`：
  - 若 `status==awaiting_payment` 且 `now >= expires_at`：
    - `UPDATE orders SET status='cancelled', cancel_reason='expired' WHERE id=? AND status='awaiting_payment'`
    - `rowcount==1` 才 `release_stock`
  - 不引入 Redis / MQ / BackgroundTasks 延迟队列 / 周期扫描

### 6. 取消与并发

| 状态 | 买家 cancel | 卖家（本店主）cancel | 库存 |
|------|-------------|----------------------|------|
| awaiting_payment | ✓ | ✓ | 释放（条件更新成功时） |
| confirmed | ✓ | ✓ | 释放 |
| shipped | ✓ | ✓ | 释放（演示简化） |
| completed | ✗ → 409 | ✗ → 409 | 不动 |
| cancelled | ✗ → 409 | ✗ → 409 | 不动 |

取消：

```text
UPDATE orders SET status='cancelled', cancel_reason=...
WHERE id=? AND status IN ('awaiting_payment','confirmed','shipped')
→ rowcount==1 才 release_stock
```

与懒过期共用「先抢状态、再动库存」，避免双加回。

### 7. API

| 方法 | 路径 | 角色 | 成功 | 说明 |
|------|------|------|------|------|
| POST | `/orders` | 买家 | 201 | body: `{ items: [{product_id, qty}, ...] }` |
| GET | `/orders` | 买家 | 200 | 自己的单；`limit`/`offset` |
| GET | `/orders/{id}` | 买家或本店卖家 | 200 | 否则 404；读时懒释放 |
| POST | `/orders/{id}/pay` | 买家 | 200 | 桩；→ confirmed；过期则先释放再 409 |
| POST | `/orders/{id}/shipments` | 本店卖家 | 201 | body `{}` 或 `{note?}`；→ shipped |
| POST | `/orders/{id}/confirm-receipt` | 买家 | 200 | → completed |
| POST | `/orders/{id}/cancel` | 买家或本店卖家 | 200 | 见规则表 |
| GET | `/shops/me/orders` | 店主 | 200 | 本店订单分页 |

**支付桩**：无外部渠道；成功响应可含订单 DTO；可选假字段不强制。重复 pay → 409。

**分页**：与 catalog 对齐（默认 limit 20、最大 100）。

### 8. 包结构与挂载

```text
app/ordering/
  models.py
  schemas.py
  repository.py
  service.py
  router.py
  deps.py          # 可选：解析订单归属
```

`main.py` include ordering router。Alembic `env.py` import ordering models。

### 9. 测试策略

- `tests/ordering/` integration；support helpers（建单、pay、短 TTL）放 `tests/support/`，禁止 test 互 import
- 覆盖：创建 201、自购 403、超卖 422、跨店行 422、未上架/非 active 422、pay、shipments、confirm-receipt、cancel 释放库存、短 TTL 过期后再 pay/读单库存还原、非法迁移 409
- 提供可直接调用的 service 级 `expire_if_needed`（或等价）便于测试不依赖真实等待以外的路径——集成测仍可用 sleep + 读单触发懒释放

### 10. 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `ORDER_RESERVATION_TTL_SECONDS` | 86400 | 待支付预留时长 |

写入 `Settings` / `.env.example`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 懒释放导致过期单短期占库存 | 可接受；后续可加周期扫描，本 change 不做 |
| shipped 后 cancel 加回库存与实物不一致 | 演示简化；真物流/售后另 change |
| 多行预留部分成功 | 同一事务；任一行条件更新失败整单回滚 |
| catalog/ordering 事务边界 | 共享同一 `AsyncSession`（现有 FastAPI Depends），service 编排不跨进程 |
| 架构文档旧三态与实现不一致 | 本 change 结束时更新 architecture.md |

## Migration Plan

1. `alembic revision` 005：`orders` + `order_items`
2. 部署：`alembic upgrade head`；无数据回填
3. 回滚：`downgrade` 删表（无生产依赖时）

## Open Questions

无阻塞项。卖家发起、`initiated_by` 字段留待下一 change（本表可不预留该列）。
