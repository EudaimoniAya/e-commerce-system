## Context

MVP 已交付 user / catalog / ordering + infra。架构文档 Phase 2 规划 **engagement 域**（收藏、浏览）；ADR-009 明确 engagement（MySQL 行为数据）优先于 AI/Redis 扩展。本 change 仅交付 **用户商品收藏**，作为 engagement 域首个垂直切片与后续推荐的数据前置。

收藏与 ordering 购物车对比：

| | 购物车 `cart_items` | 收藏 `user_favorites` |
|---|---|---|
| 域 | ordering | engagement |
| 语义 | 购买意图 | 用户偏好 |
| 唯一约束 | `(user_id, product_id)` + qty | `(user_id, product_id)` |
| 影响库存/订单 | checkout 建单 | 无 |

跨域纪律：engagement → `catalog.service` + schema；禁止 import catalog ORM/repository（ADR-001、`.cursor/rules/cross-domain-imports.mdc`）。

## Goals / Non-Goals

**Goals:**

- 可演示闭环：收藏 → 分页列表（可展示 / 失效分类）→ 单删 / 批量 batch-delete（前端提交 product_ids）
- `user_favorites` 表（migration `009`）；engagement 域标准分层
- catalog 新增 `EngagementProduct` DTO + `get_products_for_engagement`；repository 与 `get_purchasable_products` 共用批量 SQL
- TDD + AsyncClient integration；422/401/404 与既有域约定一致
- 分页复用 infra `PaginationParams` / `Paginated` envelope（`total` 计 favorite 全行）

**Non-Goals:**

- 浏览事件、推荐 API、support 对话、ADR-010 文档
- 收藏分组/标签、公开页、与 cart 联动
- 修改 catalog 公开 GET 404 语义
- media 域 DTO 重构（`image_url` 过渡期读 `products.image_url`）
- 服务端「清空 unavailable」专用 API

## Decisions

### 1. engagement 域模块（单 router）

```text
app/engagement/
  router.py       # /favorites*
  service.py      # FavoriteService：CRUD + classify + batch_delete
  repository.py
  models.py       # UserFavorite
  schemas.py
  deps.py
```

### 2. 数据模型（engagement 域）

#### `user_favorites`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `user_id` | CHAR(36) | FK 语义 → `users.id` |
| `product_id` | CHAR(36) | FK 语义 → `products.id`；仅存 ID |
| `created_at` | DATETIME | 收藏时间 |

约束：`UNIQUE(user_id, product_id)`。索引：`ix_user_favorites_user_id`（列表按 `created_at DESC` 排序）。

- **不**存 price/name/image 快照
- **不**声明跨域 SQLAlchemy relationship

migration：`009_engagement_favorites.py`（head 当前为 `008_user_phone`）。

### 3. API（JWT 隐式用户，与 `/cart` 一致）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/favorites` | `{ "product_id" }` |
| DELETE | `/favorites/{product_id}` | 按商品取消 |
| GET | `/favorites` | `?limit=&offset=` |
| POST | `/favorites/batch-delete` | `{ "product_ids": [...] }` 批量取消 |

### 4. HTTP 状态码

| 场景 | 码 |
|------|-----|
| 未认证 | 401 |
| POST 首次收藏 | 201 |
| POST 重复收藏（幂等） | 200 |
| POST 商品不存在 | 422 |
| DELETE 成功 | 204 |
| DELETE 未收藏 | 404 |
| batch-delete 成功 | 200 |
| batch-delete 空 product_ids | 422 |

### 5. POST 校验：catalog 行存在即可

- 调用 `catalog.service.get_products_for_engagement([product_id])`；结果为空 → **422**
- **不要求** `is_published` 或 shop active（偏好 ≠ 可购）
- 与 cart 加购（存在即可写入）一致；与 cart checkout（必须可购）不同

### 6. GET 列表：items + unavailable_items

**分类逻辑**（与 cart `invalid_items` 同源，命名改为 `unavailable_items`）：

1. 分页读 `user_favorites`
2. 批量 `get_products_for_engagement(product_ids)`
3. 对每个 favorite：
   - map 无命中 → `unavailable_items`，`reason=not_found`
   - `!is_published` → `unavailable_items`，`reason=product_unpublished`
   - `!shop_active` → `unavailable_items`，`reason=shop_closed`
   - 否则 → `items`

**响应字段：**

- `FavoriteItem`（items）：`id`, `product_id`, `created_at` — **不含** product 详情；前端对 items 调公开 `GET /products/{id}`
- `UnavailableFavoriteItem`（unavailable_items）：上列 + `reason` + `product_name` + `image_url`（可空；来自 `EngagementProduct` 读时 enrichment，非 DB 快照）

**分页 envelope：**

```json
{
  "items": [...],
  "unavailable_items": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

`total` = 该用户 **全部** favorite 行数（含 unavailable）。分类逻辑抽为 `FavoriteService._classify_favorites(...)`，供 GET 列表使用。

**替代方案（未采用）：** 改 catalog 公开 API 区分 404 — 破坏买家可见性契约；前端 diff catalog — 无法区分未上架与不存在。

### 7. POST /favorites/batch-delete

对标 `POST /orders/batch-pay`：前端负责编排（如从 `unavailable_items` 收集 `product_id`），后端只处理提交的 id 列表。

- body：`{ "product_ids": ["uuid", ...] }`；`product_ids` 为空 → **422**（与 batch-pay 空 `order_ids` 一致）
- 删除当前用户收藏中 `product_id ∈ product_ids` 的行；**单事务** commit
- 未收藏过的 `product_id` **跳过**（不 404）；`deleted_count` 为实际删除行数
- 响应 `{ "deleted_count": N }`；N=0 仍 200（例如提交的 id 均不在收藏中）
- **不**删除未出现在 `product_ids` 中的 favorite（含 items 侧）

**替代方案（未采用）：** `POST /favorites/purge-unavailable` 服务端推断全部 unavailable — 与 batch-pay「前端提交 id 列表」模式不一致。

### 8. catalog 跨域扩展（无 HTTP 路由）

#### DTO：`EngagementProduct`（`catalog/schemas.py`）

```python
class EngagementProduct(BaseModel):
    """跨域 DTO：供 engagement 域收藏列表 enrichment 使用。"""

    id: str
    shop_id: str
    shop_name: str
    name: str
    price: str
    image_url: str | None  # 过渡期；media 域完成后重构
    is_published: bool
    shop_active: bool
```

#### Service：`get_products_for_engagement(product_ids: list[str]) -> list[EngagementProduct]`

- 输入 id 列表；**仅返回 DB 存在的行**；不过滤上架/店状态
- 空列表输入 → 返回 `[]`

#### Repository 复用

```text
ProductRepository.fetch_products_with_shop_by_ids(ids)  # 内部共用 Row
  ├─ get_purchasable_products()      → PurchasableProduct（ordering，行为不变）
  └─ get_products_for_engagement()   → EngagementProduct（engagement）
```

Repository 返回 Row/dict；各 service 方法各自映射 DTO。**不**对外 export repository。

**替代方案（未采用）：** engagement 继续误用 `get_purchasable_products` — 命名/DTO 语义错误且缺 `image_url`。

### 9. 跨域 import

```text
✓ from catalog.service import ShopService
✓ from catalog.schemas import EngagementProduct
✗ from catalog.models / catalog.repository
```

### 10. 测试与支持层

- `tests/engagement/test_favorites_crud.py` — POST/DELETE/401/422/404/幂等
- `tests/engagement/test_favorites_list.py` — 分页、分类、unavailable enrichment、倒序
- `tests/engagement/test_favorites_batch_delete.py` — batch-delete 子集删除、跳过未收藏 id、422/401
- `tests/support/helper/engagement.py` + `results.py`
- AsyncClient；禁止 TestClient

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 提交的 product_id 部分未收藏 | 跳过并计入 deleted_count 仅实际删除数 |
| `EngagementProduct.image_url` 与 media 域演进冲突 | docstring + Non-goals 标注过渡期；后续独立 refactor change |
| `get_purchasable_products` 与 `fetch_*`  refactor 回归 ordering | apply 后跑全量 `tests/ordering/` |
| unavailable 含 `not_found`（MVP 无 DELETE 商品 API，少见） | 保留 reason 枚举与 cart 一致 |
| 列表 classify 对每页 batch 调 catalog | 单页 limit≤100；与 cart 相同模式 |

## Migration Plan

1. `devbox run -- task db:up && devbox run -- task migrate`（migration `009`）
2. 部署后新 API 可用；无 backfill（新表空库起步）
3. 回滚：`alembic downgrade -1` + 移除 router 挂载（无数据依赖其他域）

## Open Questions

- （无阻塞项）browse change 结束后再统一审视跨域 DTO 命名与 repository 复用是否需 ADR 级文档。
