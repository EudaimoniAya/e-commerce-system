## Context

catalog 与 ordering 已有四个 GET 分页列表端点，但实现纪律不统一：

| 端点 | 入参解析 | Service 二次 clamp | ORM→DTO | 外壳组装 | Repository count |
|------|----------|-------------------|---------|----------|------------------|
| `GET /products` | Router 内联 Query | ✓ service | Service | Service | `func.count()` |
| `GET /shops/me/products` | 同上 | ✓ | Service | Service | `func.count()` |
| `GET /orders` | Router Depends | ✗ | **Router** `_to_response` | **Router** | `len(全量)` ⚠️ |
| `GET /shops/me/orders` | 同上 | ✗ | **Router** | **Router** | `len(全量)` ⚠️ |

`limit`/`offset`/`total` 全程为 `int`，Repository 均为 `(list[ORM], int)`；混乱点在 **DTO 转换层** 与 **Paginated 组装层** 的分叉。架构文档（`docs/architecture.md`）将分页标为 infra「后期」；catalog-shop change 曾 defer 分页基础设施。

本 change 交付 infra 分页并迁移四端点；详细重构叙事与对比表写入 **`docs/decision/infra分页与列表数据流.md`**（长期 ADR）；`docs/architecture.md` 仅简短更新。

## Goals / Non-Goals

**Goals:**

- 提供 `app/infra/pagination/`：`PaginationParams`、`get_pagination_params`、`Paginated[TResponse]`、常量
- 统一四列表端点：Router 用 infra Depends；Service 返回 `Paginated[TResponse]`；Repository `(list[ORM], int)` + `func.count()`
- 域 schema 使用 thin subclass（Decision 8）；删除 **catalog service** `_clamp_pagination`
- 文档：OpenSpec spec、ADR、architecture 摘要、`.cursor/rules` 分页纪律
- 现有 integration 测试保持绿（HTTP 行为等价）

**Non-Goals:**

- cursor / page+size 分页；sort / filter 参数
- Repository 泛型 paginate helper
- catalog / ordering 列表 **N+1** 性能优化（迁移前已存在）
- `DEFAULT_PAGE_LIMIT` / `MAX_PAGE_LIMIT` 环境变量化
- ordering **非列表**端点的 `_to_response` 全面下沉（见下方 **半统一状态**）
- media、Redis 业务、DB migration

## Decisions

### 1. 泛型参数命名为 `TResponse`

`Paginated[TResponse]` 中 `TResponse` 表示 `items` 每个元素为 **API Response DTO**（如 `ProductResponse`），一眼区分于 ORM。域内：

域内使用 **thin subclass**（Decision 8）保留 OpenAPI 名称，例如：

```python
class PaginatedProducts(Paginated[ProductResponse]):
    model_config = ConfigDict(title="PaginatedProducts")
```

### 2. 入参：`Annotated` + `Query`，常量仅 infra 一处

```python
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

LimitQuery = Annotated[int, Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)]
OffsetQuery = Annotated[int, Query(default=0, ge=0)]
```

`get_pagination_params` SHALL 返回 **`PaginationParams` Pydantic model**（字段 `limit: int`、`offset: int`），**禁止**返回 `tuple`（避免 `limit, offset = pagination` 与 model 解构混淆导致 TypeError）。

Router 使用 `Depends(get_pagination_params)`，以 **`params.limit` / `params.offset`** 传入 Service；Service 接收两个 `int`（已校验，**不再 clamp**）。

```python
async def list_products(
    params: PaginationParams = Depends(get_pagination_params),
    ...
) -> PaginatedProducts:
    return await service.list_public_products(limit=params.limit, offset=params.offset)
```

### 3. 层职责（列表路径）

```
Router  → Depends(get_pagination_params) → service(limit, offset) → 透传 Paginated[TResponse]
Service → repo → _to_xxx_response → Paginated[TResponse](items, total, limit, offset)
Repo    → (list[ORM], total)；func.count()；limit/offset 必传无默认
```

**ordering count 写法**（单表，无需 catalog 的 subquery 模式）：

```python
total = await session.scalar(
    select(func.count()).select_from(Order).where(Order.buyer_user_id == uid)
)
```

### 4. ordering 列表：Service 内 ORM→DTO

`list_buyer_orders` / `list_shop_orders` 改为返回 `PaginatedOrders`。列表路径在 service 内完成 DTO 转换。

**双路径 DTO（#7 缓解）**：本 change **不**迁移非列表 router 的 `_to_response`，但 **建议**（optional task）将列表 service 内的 ORM→DTO 逻辑与 router `_to_response` **提取为同一模块级函数**（如 `ordering/schemas.py` 或 `ordering/converters.py` 的 `order_to_response`），router 与非列表 handler 继续调用该函数——零 HTTP 行为变更，降低字段漏改风险。若时间紧可 defer 至 follow-up `ordering-dto-in-service`。

### 5. ⚠️ 半统一状态（刻意保留，禁止本 change 顺手改全）

| 路径 | ORM→DTO 位置 | 本 change 范围 |
|------|-------------|----------------|
| **列表** `GET /orders`、`GET /shops/me/orders` | **Service** → `PaginatedOrders` | ✓ 必须迁移 |
| **非列表** create/get/pay/cancel/ship/batch-pay 等 | **Router** `_to_response` | ✗ **不迁移** |

**原因**：非列表端点全面下沉 DTO 会扩大 refactor 至 ordering 全域，超出 infra-pagination 垂直切片。

**Follow-up**：独立 change（如 `ordering-dto-in-service`）将 `_to_response` 下沉 service，消除半统一。

**Apply 纪律**：实现时 **禁止** 修改 ordering 非列表 router handler 的 `_to_response` 调用方式；design/tasks 与 ADR 均记录此项，防止 AI 顺手「统一」。

### 6. 默认排序

各域 Repository 维持 `order_by(...created_at.desc())`；spec 声明 sort 非 infra 职责，本 change 不做。

### 7. 两个 `_clamp_pagination` 不可混淆

| 位置 | 函数行为 | 本 change |
|------|----------|-----------|
| **catalog service** `_clamp_pagination` | `min(max(limit,1), MAX)` 二次钳制 | **删除**（Task 2.2） |
| **ordering router** `_clamp_pagination` | Depends + Query 透传，无额外钳制 | **删除**，改 infra Depends（Task 3.4） |

二者名称相同、职责不同；tasks 必须按域区分，禁止笼统写「删除 _clamp_pagination」。

### 8. OpenAPI schema 名称稳定

纯 `PaginatedProducts = Paginated[ProductResponse]` type alias 可能导致 OpenAPI 生成名为 `Paginated_ProductResponse_` 等，破坏现有文档/客户端。

**缓解（apply 时二选一，推荐 A）**：

- **A（推荐）**：thin subclass 保留对外名称：

  ```python
  class PaginatedProducts(Paginated[ProductResponse]):
      model_config = ConfigDict(title="PaginatedProducts")
  ```

- **B**：alias + 在 router `response_model` 显式绑定并保持现有独立 class 名（若 A 与 Pydantic v2 泛型配合有问题时的退路）

`response_model=PaginatedProducts` / `PaginatedOrders` SHALL 在 OpenAPI 中仍显示原名称。

### 9. 文档分层

| 文档 | 内容 |
|------|------|
| `docs/decision/infra分页与列表数据流.md` | 重构前后对比、为何引 infra、半统一与技术债 |
| `docs/architecture.md` | infra 行更新「分页已实现」+ 链接 ADR |
| `.cursor/rules/pagination-discipline.mdc` | 层职责与半统一禁令 |

## Risks / Trade-offs

- **[Risk] ordering 列表与非列表 DTO 转换位置不一致** → 半统一写入 ADR + cursor rule + tasks Non-goals；follow-up change 跟踪
- **[Risk] 删除 catalog `_clamp_pagination` 后仅依赖 Query 422** → 与 ordering 当前行为一致；infra 单测覆盖边界
- **[Risk] 泛型 OpenAPI 名称** → Decision 8：thin subclass + `title`，或等价方案
- **[Risk] N+1（catalog categories / ordering items）** → 迁移前已存在；Non-goals 明确不修复；follow-up perf change
- **[Risk] apply 时改动面跨 catalog + ordering** → 先红测试（若需）再迁移；四端点 integration 回归

## Migration Plan

1. 新增 `app/infra/pagination/` + `tests/infra/test_pagination.py`（红→绿）
2. 域 schema 改 thin subclass（Decision 8）；catalog 删 **service** `_clamp_pagination`、router 改 Depends
3. ordering：repo `func.count()`；两列表 service 返回 `PaginatedOrders`；router 列表变薄
4. **不碰** ordering 非列表 router 的 `_to_response`
5. 写 ADR、更新 architecture、添加 cursor rule
6. `devbox run -- task ci` 全绿

**Rollback**：revert 单 commit；无 DB 变更。

## Open Questions

无。泛型名、半统一 scope、文档路径已在 propose 阶段定稿。
