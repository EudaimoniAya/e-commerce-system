# engagement-browse

## Purpose

engagement 域用户商品浏览记录垂直切片：认证用户在商品详情页记录浏览（202 + BackgroundTasks upsert）、分页历史（items + unavailable_items）、单条删除、配置化 top N + retention 定时 trim。表：`user_browse_history`（新 migration）。跨域读路径调用 `catalog.service.get_products_for_engagement` → `EngagementProduct`；禁止 import catalog ORM/repository。

## ADDED Requirements

### Requirement: user_browse_history table

系统 SHALL 在 **engagement 域** 拥有 `user_browse_history` 表（新 migration，依赖当前 Alembic head）。每行 SHALL 表示一用户对一商品的浏览足迹；SHALL NOT 声明跨域 SQLAlchemy relationship。

#### Scenario: user_browse_history 表包含必需字段

- **WHEN** 查询 `user_browse_history` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`user_id`、`product_id`、`first_viewed_at`、`last_viewed_at`、`view_count`（INT）
- **AND** SHALL 有 `UNIQUE(user_id, product_id)`

### Requirement: Browse configuration

系统 SHALL 从环境变量读取浏览配置（`app/infra/config.py`）：

- `BROWSE_HISTORY_MAX_PER_USER`（默认 50）— trim 每用户保留最近 N 条
- `BROWSE_HISTORY_RETENTION_DAYS`（默认 30）— retention 为 `timedelta(days=N)`
- `BROWSE_DEBOUNCE_SECONDS`（默认 5）— debounce 窗口

#### Scenario: 测试环境使用较小 MAX_PER_USER

- **WHEN** `APP_ENV_FILE=.env.test` 且其中 `BROWSE_HISTORY_MAX_PER_USER=3`
- **THEN** trim 逻辑 SHALL 以 3 为 top N 上限（非硬编码 50）

### Requirement: Authenticated browse API

系统 SHALL 提供浏览 API（均需 Bearer 认证）。未认证 SHALL 返回 **401**。URL SHALL NOT 包含 `{user_id}`；当前用户 SHALL 由 JWT `sub` 解析。

#### Scenario: 未认证 POST 返回 401

- **WHEN** 未认证客户端 `POST /browse`
- **THEN** 响应状态码 SHALL 为 401

#### Scenario: 未认证 GET 返回 401

- **WHEN** 未认证客户端 `GET /browse`
- **THEN** 响应状态码 SHALL 为 401

### Requirement: POST /browse

系统 SHALL 提供 `POST /browse`，body `{ "product_id": "<uuid>" }`。校验通过后 SHALL 通过 **BackgroundTasks** 异步 upsert；HTTP 响应 SHALL 为 **202 Accepted**，body `{ "accepted": true }`。

#### Scenario: 首次浏览受理

- **WHEN** 认证用户 POST 且 `product_id` 在 catalog 存在、该用户尚无此 browse 行
- **THEN** 响应状态码 SHALL 为 202
- **AND** body SHALL 为 `{ "accepted": true }`
- **AND** BackgroundTask 完成后 SHALL 创建行：`first_viewed_at` 与 `last_viewed_at` 均为写入时刻，`view_count=1`

#### Scenario: 商品不存在返回 422

- **WHEN** 认证用户 POST 的 `product_id` 在 catalog 中不存在
- **THEN** 响应状态码 SHALL 为 422
- **AND** SHALL NOT 调度 BackgroundTask

#### Scenario: 未上架商品允许记录浏览

- **WHEN** 认证用户 POST 的 `product_id` 对应商品存在但 `is_published=false`
- **THEN** 响应状态码 SHALL 为 202
- **AND** BackgroundTask 完成后 SHALL upsert browse 行

#### Scenario: debounce 内仅更新 last_viewed_at

- **WHEN** 认证用户已有 browse 行，且 `now - last_viewed_at <= BROWSE_DEBOUNCE_SECONDS`
- **AND** 用户再次 POST 同一 `product_id`
- **THEN** 响应状态码 SHALL 为 202
- **AND** BackgroundTask 完成后 `last_viewed_at` SHALL 更新
- **AND** `view_count` SHALL 不变

#### Scenario: 间断重置累计 view_count

- **WHEN** 认证用户已有 browse 行，且 `now - last_viewed_at > timedelta(days=BROWSE_HISTORY_RETENTION_DAYS)`
- **AND** 用户 POST 同一 `product_id`（且超出 debounce）
- **THEN** BackgroundTask 完成后 `view_count` SHALL 为 1
- **AND** `first_viewed_at` SHALL 不变

#### Scenario: 活跃期间 view_count 递增

- **WHEN** 认证用户已有 browse 行，debounce 已过期，且距上次查看未超过 retention
- **AND** 用户 POST 同一 `product_id`
- **THEN** BackgroundTask 完成后 `view_count` SHALL 为原值 + 1
- **AND** `last_viewed_at` SHALL 更新

### Requirement: GET /browse paginated list

系统 SHALL 提供 `GET /browse`，分页 Query SHALL 符合 **infra-pagination** 契约（`limit` 默认 20、最大 100；`offset` 默认 0）。响应 SHALL 包含 `items`、`unavailable_items`、`total`、`limit`、`offset`。列表 SHALL 按 `last_viewed_at` 降序。`total` SHALL 为该用户 **全部** browse 行数（含 unavailable）。

#### Scenario: 空浏览列表

- **WHEN** 认证用户无 browse 行并 GET /browse
- **THEN** 响应 SHALL 为 `{ "items": [], "unavailable_items": [], "total": 0, "limit": 20, "offset": 0 }`（limit/offset 随 Query）

#### Scenario: 可展示浏览在 items

- **WHEN** browse 对应商品存在、已上架且店铺 active
- **THEN** 该 browse SHALL 出现在 `items`
- **AND** item SHALL 含 `id`、`product_id`、`first_viewed_at`、`last_viewed_at`、`view_count`
- **AND** item SHALL NOT 含嵌套 product 价图详情（展示由前端调公开 catalog API）

#### Scenario: 未上架商品在 unavailable_items

- **WHEN** browse 对应商品存在但 `is_published=false`
- **THEN** 该 browse SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `product_unpublished`
- **AND** SHALL 含 `product_name`（来自 catalog service enrichment）

#### Scenario: 店铺关闭在 unavailable_items

- **WHEN** browse 对应商品存在但所属店铺 `status=closed`
- **THEN** 该 browse SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `shop_closed`

#### Scenario: 商品不存在于 unavailable_items

- **WHEN** browse 的 `product_id` 在 catalog 无对应行
- **THEN** 该 browse SHALL 出现在 `unavailable_items`
- **AND** SHALL 含 `reason` 为 `not_found`
- **AND** `product_name` MAY 为空

### Requirement: DELETE /browse/{product_id}

系统 SHALL 提供 `DELETE /browse/{product_id}`，按商品 ID 删除浏览记录。

#### Scenario: 删除已有浏览记录

- **WHEN** 认证用户 DELETE 其已有 browse 的 `product_id`
- **THEN** 响应状态码 SHALL 为 204
- **AND** 对应 browse 行 SHALL 被删除

#### Scenario: 删除无浏览记录返回 404

- **WHEN** 认证用户 DELETE 其无 browse 的 `product_id`
- **THEN** 响应状态码 SHALL 为 404

### Requirement: Browse trim job

系统 SHALL 提供 `task browse:trim`（CLI），按配置 trim `user_browse_history`：

- 对每个 `user_id`：按 `last_viewed_at DESC` 取 top `BROWSE_HISTORY_MAX_PER_USER` 行保留
- 其余行中，`last_viewed_at < now - timedelta(days=BROWSE_HISTORY_RETENTION_DAYS)` SHALL 被删除
- top N 内行即使超过 retention SHALL 保留，直至被挤出 top N

#### Scenario: top N 内超 retention 行保留

- **WHEN** 某用户 browse 行数不超过 `BROWSE_HISTORY_MAX_PER_USER`，且某行 `last_viewed_at` 早于 retention  cutoff
- **AND** 执行 trim
- **THEN** 该行 SHALL 仍存在

#### Scenario: top N 外超 retention 行删除

- **WHEN** 某用户 browse 行数超过 `BROWSE_HISTORY_MAX_PER_USER`，最旧超出 top N 的行 `last_viewed_at` 早于 retention cutoff
- **AND** 执行 trim
- **THEN** 该行 SHALL 被删除
- **AND** 该用户剩余行数 SHALL 不超过 `BROWSE_HISTORY_MAX_PER_USER`

### Requirement: Browse list SHALL NOT auto-delete unavailable rows

GET /browse SHALL NOT 自动删除 unavailable browse 行；用户 SHALL 通过 DELETE 主动清理。

#### Scenario: GET 不删除下架商品浏览记录

- **WHEN** 商品被下架后用户 GET /browse
- **THEN** 对应 browse SHALL 仍存在于 `unavailable_items`
- **AND** DB 中 browse 行 SHALL 仍存在

### Requirement: BackgroundTasks durability boundary

POST /browse SHALL NOT 保证 at-least-once 持久化；BackgroundTasks 失败或进程崩溃 MAY 导致浏览记录丢失。系统 SHALL NOT 在本 change 引入 Outbox 补偿。

#### Scenario: 202 不表示已落库

- **WHEN** 认证用户 POST /browse 收到 202
- **THEN** 响应 SHALL NOT 被解读为 browse 行已 commit 完成
- **AND** 立即 GET 可能尚未包含该次浏览（最终一致）
