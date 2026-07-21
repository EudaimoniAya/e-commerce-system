## Context

`ordering-buyer-orders` 已归档并实现：买家 `POST /orders`、付桩、发货、收货、取消、买卖家列表与详情；FSM 五态不变；库存预留/懒释放；跨域仅经 `catalog.service`。

本 change 补齐**卖家为指定买家建单**（`ordering-seller-orders`），与 `ordering-buyer-orders` 命名对称。暂无 IM，建单时 body 显式传 `buyer_user_id`；未来聊天仅预选该字段。管理员与店主仍可作为普通买家使用 `POST /orders` 等既有路径。

## Goals / Non-Goals

**Goals:**

- 卖家 `POST /shops/me/orders` → `awaiting_payment` + `initiated_by=seller` + 库存预留/快照
- 买家 `POST /orders` 写入 `initiated_by=buyer`；`OrderResponse` 暴露 `initiated_by`
- 跨域 `user.service.get_user_summary` 校验买家存在且 active
- 双路径可见性：买家建单 → 店主列表可见；卖家建单 → 指定买家列表可见
- 列表懒释放：`GET /orders` 与 `GET /shops/me/orders` 对 `awaiting_payment` 逐单 `expire_if_needed`
- migration `006`：`orders.initiated_by` 回填 `buyer`

**Non-Goals:**

- IM、用户搜索、email/地址/联系方式扩展
- 真支付、物流、退货、周期扫描、Redis/MQ
- HTTP 403/404 统一、PATCH 发货
- 一人多店、购物车

## Decisions

### 1. 确认语义（无新状态）

| 路径 | 建单 | pay 成功 |
|------|------|----------|
| `initiated_by=buyer` | 买家意向 | `confirmed`（买家付 + **卖家隐式确认**；不同意可后续 cancel） |
| `initiated_by=seller` | **卖家已确认** | `confirmed`（**买家确认** + 付桩） |

FSM 与 change-1 完全相同；`initiated_by` 仅审计/展示，不参与迁移分支。

### 2. 数据模型（ordering 域，migration `006`）

#### `orders` 新增列

| 列 | 类型 | 说明 |
|----|------|------|
| `initiated_by` | VARCHAR(16) NOT NULL | `buyer` \| `seller`；默认 `buyer`；已有行回填 `buyer` |

`OrderResponse` 增加 `initiated_by: Literal["buyer","seller"]`。

### 3. user 域跨域读（新增）

| 组件 | 说明 |
|------|------|
| `UserSummary` schema | `id: str`, `nickname: str`（**不含 email**） |
| `UserService.get_user_summary(user_id)` | 存在且 `is_active=true` → `UserSummary`；不存在 → `HTTPException 404`；禁用 → `422` |

ordering 注入 `UserService`（与 `ShopService` 相同 Depends 模式）；**禁止** import `user.models` / `user.repository`。

### 4. 卖家建单 API

| 方法 | 路径 | 角色 | 成功 | body |
|------|------|------|------|------|
| POST | `/shops/me/orders` | 店主 | 201 | `{ buyer_user_id, items: [{product_id, qty}, ...] }` |

校验顺序（与买家建单对齐的部分复用内核）：

1. `get_current_shop` → 店 id、`owner_user_id`
2. `get_user_summary(buyer_user_id)` → 404/422
3. `buyer_user_id == owner_user_id` → **403**
4. 店 `closed` / 商品不可购 / 跨店 / 库存 → **422**
5. `reserve_stock` + insert order（`initiated_by=seller`，`shop_id=current_shop.id`）

**替代方案**：扩展 `POST /orders` 加可选 `buyer_user_id` —— 拒绝；角色与路径分离更清晰。

### 5. 服务层重构

抽取 `_create_order_core(buyer_user_id, shop_id, items, initiated_by)`（或等价私有方法）：

- 买家路由：`create_order(buyer_user_id=current_user, initiated_by="buyer")`，shop 由商品推导
- 卖家路由：`create_order_by_seller(seller_shop_id, buyer_user_id, items)`，`initiated_by="seller"`；**所有 `product_id` 必须属于 `seller_shop_id`**（非仅「彼此同店」）

库存、快照、TTL、事务边界与 change-1 一致。

### 6. 懒释放扩展

| 路径 | 行为 |
|------|------|
| `GET /orders/{id}` | 已有：单条 `expire_if_needed` |
| `GET /orders` | **新增**：返回前对每条 `awaiting_payment` 调用 `expire_if_needed` |
| `GET /shops/me/orders` | **新增**：同上 |

仍无周期扫描。列表内过期单可能在本响应中变为 `cancelled` + 库存释放。

**ORM 同步**：`expire_if_needed` 在 CAS 成功并 `commit` 后 **必须** `await session.refresh(order)`，使内存对象与库一致（含 `status`/`cancel_reason`/`updated_at`）；禁止依赖 `_to_response` 前手动改字段后仍访问未刷新的列。详情路径 deps 的 re-fetch 可保留作双保险。

### 7. 权限（卖家禁止项，不变）

| 动作 | 卖家 |
|------|------|
| pay | ✗ 403 |
| confirm-receipt | ✗ 404（买家 dep） |
| 买本店（买家路径） | ✗ 403 |
| 为本人建单（卖家路径） | ✗ 403 |

管理员无特殊豁免；可当买家被卖家指定。

### 8. 测试策略

- `tests/ordering/test_create_order_by_seller.py`（或并入现有文件）：201、404 买家、422 禁用、403 自购、401
- 扩展 `test_list_orders.py`：双路径可见性；列表触发懒释放（短 TTL）
- `tests/unit` 或 integration：`get_user_summary` 最小覆盖
- support helper：`create_order_by_seller` pipeline

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 列表逐单懒释放 N+1 / 多次 commit | 订单量小可接受；每单条件更新防双释放 |
| 无 IM 买家不知有单 | 演示靠 `GET /orders`；IM change 后补通知 |
| `UserService` 注入 ordering 增加耦合 | 符合跨域 service 纪律；仅只读 |
| MODIFIED spec 归档合并 | delta 写全 requirement 块 |
| 买家状态 TOCTOU（验 active 与插单之间） | MVP 接受；低概率，与库存竞争同类 |
| ordering 跨域 import 历史债 | 本 change 移除 `catalog.models.Shop`；后续域改动顺手清类似违规 |

## Migration Plan

1. `alembic revision` 006：`ALTER TABLE orders ADD initiated_by VARCHAR(16) NOT NULL DEFAULT 'buyer'`
2. 部署：`alembic upgrade head`
3. 回滚：`downgrade` 删列（无依赖时）

## Open Questions

无阻塞项。
