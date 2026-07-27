# ADR-006：Infra 分页与列表数据流

- **状态**：已采纳
- **日期**：2026-07-27
- **背景**：catalog 与 ordering 四个 GET 列表端点在 **infra-pagination** change 之前已各自实现分页，但纪律不统一——入参解析、ORM→DTO 转换、`Paginated*` 组装位置、Repository count 写法均不一致。catalog-shop change 曾 defer「分页基础设施」；架构文档原将分页标为 infra「后期」。在 engagement 等 Phase 2 域需要列表 API 之前，先交付 **infra 分页契约** 并迁移现有四端点，避免后续实现继续随机发挥。

## 为何需要 infra 分页

分页在概念上简单（`limit` / `offset` / `total`），但在单体多域里会同时触及 **Router / Service / Repository** 三层。若各域自行约定，会出现：

- 同名函数、不同语义（如两个 `_clamp_pagination`）
- 同一 HTTP 契约、不同 Python 数据流（catalog 在 service 拼外壳，ordering 在 router 拼）
- 重复 schema（`PaginatedProducts` 与 `PaginatedOrders` 四字段完全相同）

infra 分页提供 **无业务语义** 的横切能力（入参依赖 + 响应壳 + 常量），业务域只填 `TResponse` 元素类型与 Repository 过滤条件。与 [ADR-001 单体多域](./单体多域架构.md) 一致：业务域 → infra 公开 API；infra **不** import 业务域。

### infra 横切模块的心智模型

```
业务域（纵切）     catalog / ordering / user / engagement …
       │ 调用
       ▼
infra（横切）      config · database · redis · auth · logging · errors
                   · health · readiness · pagination · …
```

Router **可以** 直接使用 infra 的 `Depends(get_pagination_params)`（与 `get_current_user_id` 同级）；Service 接收 plain `limit: int, offset: int`，不依赖 FastAPI。

## 分页数据流：两类数据，不要混谈

| 类型 | 字段 | 各层形态 | 是否变化 |
|------|------|----------|----------|
| **控制参数** | `limit`, `offset` | 全程 `int` | 几乎不变 |
| **业务载荷** | 页内记录 + `total` | Repository：`list[ORM]`；API：`list[TResponse]` + 外壳 | **变化点** |

容易误以为「三层数据形态都在变」；实际上 **`limit`/`offset`/`total` 始终是 int**，Repository **始终是** `(list[ORM], int)`。本 change 统一的是：

1. **页内元素** 何时从 ORM 转为 Response DTO  
2. **`{items, total, limit, offset}` 外壳** 在哪一层组装  

### 请求侧 vs 响应侧

| 组件 | 作用层 | 说明 |
|------|--------|------|
| `get_pagination_params` + `Query` | **请求**（URL Query） | GET 列表无 body；解析 `?limit=&offset=` |
| `Paginated[TResponse]` | **响应**（JSON body） | `items` 元素为 API DTO，**不是** ORM |

二者互补：一个规定「怎么要页」，一个规定「怎么还页」。

## 迁移前后四端点对比

| 端点 | 迁移前入参 | 迁移后入参 | Service 二次 clamp | ORM→DTO | Paginated 组装 | Repository count |
|------|-----------|-----------|-------------------|---------|---------------|------------------|
| `GET /products` | Router 内联 Query | `Depends(get_pagination_params)` | ✓ 有（已删） | Service | Service | `func.count()` |
| `GET /shops/me/products` | 同上 | 同上 | ✓ 有（已删） | Service | Service | `func.count()` |
| `GET /orders` | Router `_clamp_pagination`（tuple） | `Depends(get_pagination_params)` | 无 | **Router** → **Service** | **Router** → **Service** | `len(全量)` → **`func.count()`** |
| `GET /shops/me/orders` | 同上 | 同上 | 无 | 同上 | 同上 | 同上 |

### 两个 `_clamp_pagination` 不可混淆

| 位置 | 行为 | 本 change |
|------|------|-----------|
| **catalog service** `_clamp_pagination` | `min(max(limit,1), MAX)` 二次钳制 | **删除** |
| **ordering router** `_clamp_pagination` | Depends + Query 透传，无额外钳制 | **删除**，改 infra Depends |

名称相同、职责不同；笼统写「删除 _clamp_pagination」容易删错层。

## 标准层职责（列表路径）

```
Client  ?limit=20&offset=0
    │
    ▼
Router   Depends(get_pagination_params) → params.limit / params.offset
         → service(limit, offset) → 透传 Paginated[TResponse]
    │
    ▼
Service  repo(limit, offset) → _to_xxx_response → Paginated[TResponse](…)
    │
    ▼
Repo     SQL limit/offset + func.count() → (list[ORM], total)
```

- **Repository**：只做 SQL 分页与计数；**不**定义默认 `limit`/`offset`（由上层必传）。
- **Service**：列表路径负责 ORM→DTO 与组装 `Paginated[TResponse]`；**禁止**二次 clamp。
- **Router**：列表路径 **禁止** 手动 `Paginated(...)` 或 `_to_response`。

默认排序 **不在 infra**：各域 Repository 维持 `order_by(created_at.desc())`；sort/filter 参数留待业务 change。

## 设计决策

### 决策 1：`PaginationParams` 为 Pydantic BaseModel，禁止 tuple

`get_pagination_params` 返回 `PaginationParams`（`limit: int`, `offset: int`）。Router 使用 **`params.limit` / `params.offset`**。

虽 Pydantic v2 双字段 model 在语法上可能被解构，但 **设计合约禁止** `limit, offset = params`，以免与历史上 ordering 的 `tuple[int, int]` Depends 混淆导致 TypeError。

Service 接收两个 `int`（已由 Query 校验），不再 clamp。

### 决策 2：常量仅在 infra 定义，本 change 不环境变量化

`DEFAULT_PAGE_LIMIT = 20`、`MAX_PAGE_LIMIT = 100` 定义于 `app/infra/pagination/deps.py`（或 `constants.py`），作为 `Annotated[..., Query(...)]` 默认值。运维按环境调整限制需改源码；若未来需要，单独 change 迁入 `Settings`。

### 决策 3：Repository 使用 `func.count()`，禁止 `len(全量 ORM)`

ordering 迁移前使用 `len(total_result.scalars().all())`，大表会物化全部 ORM 行。

**ordering 单表**（无需 catalog 的 subquery）：

```python
total = await session.scalar(
    select(func.count()).select_from(Order).where(Order.buyer_user_id == uid)
)
```

catalog 带 join/filter 的列表可继续 subquery + `func.count()` 模式。

### 决策 4：`Paginated[TResponse]` 泛型 + thin subclass

`TResponse` 表示 `items` 每个元素为 **API Response DTO**（如 `ProductResponse`），**不是** ORM。

纯 type alias 可能导致 OpenAPI 名漂移为 `Paginated_ProductResponse_`。各域使用 **thin subclass** 保留对外名称：

```python
class PaginatedProducts(Paginated[ProductResponse]):
    model_config = ConfigDict(title="PaginatedProducts")
```

## 半统一状态（刻意保留，禁止顺手改全）

| 路径 | ORM→DTO | 说明 |
|------|---------|------|
| **列表** `GET /orders`、`GET /shops/me/orders` | **Service** `_to_order_response` | ✓ 已迁移 |
| **非列表** create/get/pay/cancel/ship/batch-pay 等 | **Router** `_to_response` | ✗ **本 change 不迁移** |

非列表全面下沉 DTO 会扩大至 ordering 全域 refactor，超出 infra-pagination 垂直切片。**Apply / 后续 AI 禁止** 以「统一」为由改动非列表 handler 的 `_to_response` 调用方式。

可选缓解：将 `_to_response` 与 `_to_order_response` 提取为同一模块级函数（零 HTTP 行为变更）——留待 follow-up。

## 既有技术债（本 change 不修复）

| 问题 | 位置 | Follow-up change |
|------|------|------------------|
| 类目 N+1 | catalog service `_load_product_categories` 逐商品查询 | `catalog-list-batch-categories` |
| 订单行 N+1 | ordering service 列表路径逐单 `list_by_order_id` | `ordering-list-batch-items` |
| DTO 双路径 | 列表 service vs 非列表 router 各一套转换 | `ordering-dto-in-service` |

迁移 **不引入** 上述 N+1；DTO 搬到 service 仅改变列表路径的组装位置，items 加载模式与迁移前相同。

## HTTP vs Python 层变更说明

- **HTTP/API**：四列表端点 JSON 字段与状态码 **等价**，无 breaking change。
- **Python**：ordering `list_buyer_orders` / `list_shop_orders` 由 `tuple[list[Order], int]` 改为 `PaginatedOrders`；当前无生产/测试代码直调这两 method。

## 涉及文件

- `app/infra/pagination/` — `PaginationParams`、`get_pagination_params`、`Paginated[TResponse]`
- `app/catalog/` — router / service / schemas（列表已对齐）
- `app/ordering/` — router / service / repository / schemas（列表已对齐；非列表 router 仍 `_to_response`）
- `.cursor/rules/pagination-discipline.mdc` — 层职责与半统一禁令

## 相关文档

- [项目架构](../architecture.md)
- [ADR-001 单体多域架构](./单体多域架构.md)
- OpenSpec：`openspec/specs/infra-pagination/spec.md`（archive 后）
