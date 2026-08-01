## Why

电商 MVP 底座已具备 user / catalog / ordering，但缺少 **用户偏好（收藏）** 行为数据；该能力是 engagement 域的第一步，也是后续 AI 推荐系统的主信号来源之一（与 `order_items` 购买信号并列）。收藏与 ordering 域购物车语义不同：购物车是购买意图暂存，收藏是长期偏好；本 change 交付可演示的收藏 CRUD + 失效项处理 + 批量清理闭环。

## What Changes

- 新建 **engagement 域**：`user_favorites` 表（migration `009`）；`router → service → repository → model + schemas + deps`
- **收藏 API**（均需 Bearer 认证；URL 不含 `user_id`，与 `/cart`、`/orders` 一致）：
  - `POST /favorites` — body `{ "product_id" }`；商品在 catalog 存在即可（不要求可购/可展示）
  - `DELETE /favorites/{product_id}` — 取消单条收藏
  - `GET /favorites` — 分页列表；`items`（可公开展示）+ `unavailable_items`（含 `reason` 与展示字段）
  - `POST /favorites/purge-unavailable` — 一键删除当前用户所有 `unavailable_items` 对应收藏行
- **跨域读路径**：engagement 调用 **catalog.service** `get_products_for_engagement` → `list[EngagementProduct]`；**不**新增 catalog HTTP 路由；**不** import catalog ORM/repository
- **catalog 最小扩展**：新增跨域 DTO `EngagementProduct` 与 service 方法；与既有 `get_purchasable_products` **共用** repository 批量查询实现
- **`GET /favorites` 列表策略**：`items` 仅含 favorite 元数据（前端对可展示项再调公开 `GET /products/{id}`）；`unavailable_items` 由 engagement 服务端 enrichment（含 `product_name`、`image_url`），避免前端无法区分 catalog 404（未上架 vs 不存在）
- 扩展 **pytest**：`tests/engagement/` + `tests/support/helper/engagement.py`
- 更新 **docs/architecture.md**（engagement 收藏部分）

## Non-goals

- 不实现浏览事件（`browse_events`）— 留给后续 `engagement-browse-events` change
- 不实现收藏分组 / 标签 / 备注 / 公开收藏页 / 查他人收藏
- 不实现推荐 API、AI Tool、与购物车联动（收藏 ≠ 加购）
- 不修改 catalog 公开 API 404 语义（未上架仍对买家不可见）
- 不新增 ADR-010（跨域 DTO 规范文档）；本 change 在 design/spec 内自洽，浏览 change 结束后再统一审视
- 不做 media 域 DTO 重构（`EngagementProduct.image_url` 为过渡期字段）
- `POST /favorites/purge-unavailable` 不支持按 `reason` 子集过滤（MVP 清理全部 unavailable）
- 不实现 `GET /favorites/{product_id}` 查是否已收藏（可后续 enhancement）

## Capabilities

### New Capabilities

- `engagement-favorites`：用户商品收藏 CRUD、分页列表（items + unavailable_items）、批量 purge unavailable

### Modified Capabilities

- `catalog-products`：新增跨域 service 方法 `get_products_for_engagement` 与 DTO `EngagementProduct`（无 HTTP 路由；repository 与 `get_purchasable_products` 共用批量查询）

## Impact

- **业务域**：`engagement`（新建）；`catalog`（service + schemas + repository 内部复用，无对外 REST 变更）
- **跨域**：engagement → `catalog.service.get_products_for_engagement` + `EngagementProduct` schema
- **新增/修改**：`app/engagement/*`、`app/catalog/service.py`、`app/catalog/schemas.py`、`app/catalog/repository.py`（抽取共用 fetch）、`alembic/versions/009_*.py`、`app/main.py`、`tests/engagement/`、`tests/support/`、`docs/architecture.md`
- **API**：新增 `/favorites*`；现有 catalog / ordering / user API 不变
- **分支**：基于 `dev` 的 `feature/engagement-favorites`
