## Why

catalog 与 ordering 域已有四个分页列表端点，但分页入参解析、ORM→DTO 转换与 `Paginated*` 响应组装分散在各域且实现不一致（catalog 在 service 完成，ordering 在 router 完成；常量与 count 写法亦重复）。架构文档将分页标为 infra「后期」能力，而 engagement 等 Phase 2 域即将需要统一契约。现需在继续扩展业务域之前，交付 **infra 分页基础设施** 并迁移现有列表端点，避免后续 AI/人工实现继续随机发挥。

## What Changes

- 新增 **`app/infra/pagination/`**：`DEFAULT_PAGE_LIMIT` / `MAX_PAGE_LIMIT` 常量、`PaginationParams`、`get_pagination_params`（`Annotated` + `Query`）、泛型响应壳 **`Paginated[TResponse]`**
- **迁移四个列表端点**（`GET /products`、`GET /shops/me/products`、`GET /orders`、`GET /shops/me/orders`）统一使用 infra 分页依赖；**Service 层** 组装 `Paginated[TResponse]` 并负责列表路径的 ORM→DTO
- **ordering** 两个列表 service method 改为返回 `PaginatedOrders`；**ordering 非列表端点** 仍在 router 使用 `_to_response`（**刻意保留的半统一状态**，见 design）
- **catalog** 删除 service 层 `_clamp_pagination`（避免与 Query 双重钳制）
- **ordering repository** count 改为 `func.count()`（替代 `len(全量 ORM)`）
- 各域 `PaginatedProducts` / `PaginatedOrders` 基于 **`Paginated[TResponse]`** 定义（thin subclass 或等价 alias + OpenAPI title，见 design Decision 8）
- 新增 **`tests/infra/test_pagination.py`** 单元测试
- 新增 **`openspec/specs/infra-pagination/spec.md`**；更新 catalog-products / ordering-buyer-orders delta（分页引用 infra 契约）
- 新增 **`docs/decision/infra分页与列表数据流.md`**（重构过程、域间差异、半统一状态与技术债）；**`docs/architecture.md`** 简短更新 infra 分页已实现
- 新增 **`.cursor/rules/pagination-discipline.mdc`** 分页纪律

## Non-goals

- **不** 实现 cursor / page+size 分页（维持 `limit`/`offset`）
- **不** 实现 sort / filter 查询参数（列表默认 `created_at DESC` 写在各域 repository；本 change 不扩展 sort infra）
- **不** 将 ordering **非列表**端点（create/get/pay/cancel/batch-pay 等）的 `_to_response` 下沉 service（**follow-up change**，本 change 仅记录 tech debt）
- **不** 引入 Repository 泛型 paginate helper（YAGNI）
- **不** 修改 media 上传、Redis 业务用法、数据库 schema
- **不** 改变四个列表端点对外 JSON 字段名或 HTTP 状态码语义（**HTTP/API 行为等价 refactor**）；ordering 列表 service method 签名由 `tuple[list[Order], int]` 改为 `PaginatedOrders` 属 **Python 层 breaking**，当前无生产/测试代码直调 service 列表 method
- **不** 修复 catalog 类目加载或 ordering items 加载的 **N+1**（迁移前已存在，见 follow-up）
- **不** 将 `DEFAULT_PAGE_LIMIT` / `MAX_PAGE_LIMIT` 迁入 `Settings` 环境变量（硬编码常量即可）

## Capabilities

### New Capabilities

- `infra-pagination`: 分页 Query 依赖、`PaginationParams`、`Paginated[TResponse]`、常量约定、层职责与列表默认排序说明

### Modified Capabilities

- `catalog-products`: 分页参数与响应 SHALL 引用 infra-pagination 契约（表述从「本域惯例」改为 infra 引用；HTTP 行为不变）
- `ordering-buyer-orders`: 同上；列表 lazy-expire 等行为不变

## Impact

- **业务域**: **infra**（新增 pagination 模块）；**catalog**、**ordering**（router/service/repository/schemas refactor；**HTTP 无 breaking change**）
- **新增/修改文件**: `app/infra/pagination/`、`app/catalog/`、`app/ordering/`、`tests/infra/`、`tests/catalog/`、`tests/ordering/`（最小改动）、`openspec/specs/`、`docs/decision/`、`docs/architecture.md`、`.cursor/rules/`
- **API**: 四个 GET 列表端点 Query 与响应形状不变；OpenAPI 保留 `PaginatedProducts` / `PaginatedOrders`  schema 名称（见 design Decision 8）
- **依赖**: 无新增第三方包
