## ADDED Requirements

### Requirement: Pagination query parameters

系统 SHALL 在 `app/infra/pagination/` 提供 `get_pagination_params` FastAPI 依赖，从 GET 请求的 **Query 字符串**（非 request body）解析分页参数：

- `limit`：默认 **20**，最小 **1**，最大 **100**
- `offset`：默认 **0**，最小 **0**

常量 `DEFAULT_PAGE_LIMIT` 与 `MAX_PAGE_LIMIT` SHALL 随 `get_pagination_params` 在 `deps.py` 定义（**本 change 不**迁入 `Settings` 环境变量），并作为 `Annotated[..., Query(...)]` 的默认值来源。

`get_pagination_params` SHALL 返回 **`PaginationParams` Pydantic `BaseModel`**（字段 `limit: int`、`offset: int`），**禁止**返回 `tuple[int, int]`。Router 通过属性访问 `params.limit` / `params.offset` 传入 Service，**禁止** `limit, offset = pagination` 元组解构。

业务域 Router SHALL 通过 `Depends(get_pagination_params)` 获取入参，**禁止**在各域重复定义默认 limit/max 或二次钳制（Service 层不得再 clamp）。

#### Scenario: 合法 Query 解析为 PaginationParams

- **WHEN** 客户端请求 `GET` 列表端点且 Query 为 `limit=20&offset=0`
- **THEN** `get_pagination_params` SHALL 返回 `PaginationParams(limit=20, offset=0)`（Pydantic model，非 tuple）

#### Scenario: limit 超出上限时校验失败

- **WHEN** 客户端请求 `GET` 列表端点且 Query 含 `limit=101`
- **THEN** 响应状态码 SHALL 为 **422**（FastAPI Query 校验）

#### Scenario: offset 为负时校验失败

- **WHEN** 客户端请求 `GET` 列表端点且 Query 含 `offset=-1`
- **THEN** 响应状态码 SHALL 为 **422**

### Requirement: Paginated response envelope

系统 SHALL 在 infra 提供泛型 Pydantic 模型 `Paginated[TResponse]`，字段为：

- `items: list[TResponse]`
- `total: int`
- `limit: int`
- `offset: int`

各业务域 SHALL 通过 **thin subclass** 保留 OpenAPI 名称（如 `class PaginatedProducts(Paginated[ProductResponse])` + `model_config title`），**禁止**重复定义同形四个字段的独立 `BaseModel`，也**不推荐**纯 type alias 导致 OpenAPI 名漂移为 `Paginated_ProductResponse_`。`TResponse` 表示 `items` 中每个元素的 **API Response DTO**，不得为 ORM 类型。

#### Scenario: OpenAPI 保留域分页 schema 名称

- **WHEN** 生成 OpenAPI 文档
- **THEN** catalog 列表 `response_model` SHALL 仍显示 **`PaginatedProducts`**（非泛型内部名）

#### Scenario: 分页响应包含回显参数

- **WHEN** 客户端以 `limit=10&offset=5` 请求任一已迁移的分页列表端点且成功返回 200
- **THEN** 响应 JSON SHALL 含 `limit=10`、`offset=5`、`total`（非负整数）及 `items` 数组

### Requirement: Layer responsibilities for paginated lists

对于使用 infra 分页的 **列表**端点，各层职责 SHALL 为：

| 层 | 职责 |
|----|------|
| Router | `Depends(get_pagination_params)` → `PaginationParams`；以 `params.limit` / `params.offset` 传 Service；**透传** Service 返回的 `Paginated[TResponse]`；**禁止**在列表路径组装 `Paginated` 或做 ORM→DTO |
| Service | 调用 Repository；列表路径用 `_to_xxx_response` 将 ORM 转为 DTO；返回 `Paginated[TResponse]` |
| Repository | 执行 SQL 分页；返回 `tuple[list[ORM], int]`；`total` SHALL 使用 `func.count()`，**禁止** `len(全量 ORM 实例)`；ordering 单表 count 用 `select(func.count()).select_from(Order).where(...)`；`limit`/`offset` 由调用方必传，Repository **不得**定义默认 limit/offset |

#### Scenario: catalog 列表 Service 返回 PaginatedProducts

- **WHEN** 客户端请求 `GET /products` 或 `GET /shops/me/products` 且成功
- **THEN** 对应 Service method SHALL 返回 `PaginatedProducts`（非裸 ORM 元组）
- **AND** Router SHALL 直接返回该对象，不在 Router 内映射 `ProductResponse`

#### Scenario: ordering 列表 Service 返回 PaginatedOrders

- **WHEN** 客户端请求 `GET /orders` 或 `GET /shops/me/orders` 且成功
- **THEN** 对应 Service method SHALL 返回 `PaginatedOrders`
- **AND** Router SHALL 直接返回该对象，不在列表路径调用 `_to_response`

### Requirement: Default list sort order

infra 分页 **不** 提供 sort 查询参数。各域 Repository 对分页列表 SHALL 默认按 **`created_at DESC`** 排序。本 change **不** 扩展 sort/filter infra。

#### Scenario: 商品列表默认按创建时间降序

- **WHEN** 客户端请求 `GET /products` 且存在多条商品
- **THEN** `items` 顺序 SHALL 按 `created_at` 降序（与迁移前行为一致）

### Requirement: Infra pagination unit tests

系统 SHALL 在 `tests/infra/test_pagination.py` 提供单元测试，覆盖 `PaginationParams` / Query 依赖的边界（无需数据库），且 **不** 依赖 `tests.support` 或 HTTP client fixture。

#### Scenario: infra 单测无 integration 依赖

- **WHEN** 运行 `uv run pytest tests/infra/test_pagination.py`
- **THEN** 用例 SHALL 可在无 MySQL/Redis 的情况下通过
