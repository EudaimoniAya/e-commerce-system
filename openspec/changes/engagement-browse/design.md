## Context

MVP 已交付 user / catalog / ordering + engagement 收藏（`user_favorites`、migration `009`）。ADR-009 明确 **MySQL engagement 行为数据** 优先于 Redis/AI 扩展；浏览记录是 Phase 2 engagement 域剩余切片，为后续推荐与 Outbox 演进提供行为底座。

浏览与收藏对比：

| | 收藏 `user_favorites` | 浏览 `user_browse_history` |
|---|---|---|
| 语义 | 长期偏好 | 近期足迹 + 兴趣强度 |
| 唯一约束 | `(user_id, product_id)` | `(user_id, product_id)` |
| 写路径 | 同步 commit | **BackgroundTasks** → 202 |
| 时间字段 | `created_at` | `first_viewed_at`、`last_viewed_at`、`view_count` |
| 容量 | 无硬上限 | top N（配置）+ trim job |

跨域纪律：engagement → `catalog.service.get_products_for_engagement` + `EngagementProduct`；禁止 import catalog ORM/repository。

## Goals / Non-Goals

**Goals:**

- 可演示闭环：商品详情页 POST 记录浏览 → GET 分页历史（items + unavailable_items）→ DELETE 误触清理
- `user_browse_history` 表（新 migration，依赖当前 Alembic head）；engagement 域扩展 `BrowseService`
- upsert 语义：间断重置累计 `view_count`；debounce（`<= 5s` 仅更新 `last_viewed_at`）
- 配置：`BROWSE_HISTORY_MAX_PER_USER`、`BROWSE_HISTORY_RETENTION_DAYS`、`BROWSE_DEBOUNCE_SECONDS`
- `task browse:trim` + unit 测试（top N 内保留 / top N 外超 retention 删除）；进 CI
- TDD + AsyncClient integration（await BackgroundTasks 完成后再 assert DB）
- 分页复用 infra `PaginationParams`；列表 envelope 对齐收藏

**Non-Goals:**

- Outbox / Celery / at-least-once（BackgroundTasks 失败可静默丢失）
- AI Tool、推荐 API、event log、batch-delete、关键词搜索
- 未登录匿名埋点、POST 路径同步 trim
- catalog DTO/HTTP 变更（复用既有 `EngagementProduct`）

## Decisions

### 1. engagement 域模块扩展

```text
app/engagement/
  router.py           # 追加 /browse*（与 /favorites* 同 router）
  service.py          # 追加 BrowseService（或同文件 BrowseService 类）
  repository.py       # 追加 BrowseRepository
  models.py           # 追加 UserBrowseHistory
  schemas.py          # BrowseItem、UnavailableBrowseItem、BrowseListResponse、BrowseAcceptedResponse
  jobs/
    trim_browse_history.py   # trim 纯函数 + CLI 入口
  deps.py             # 注入 BrowseService
```

### 2. 数据模型（engagement 域）

#### `user_browse_history`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `user_id` | CHAR(36) | FK 语义 → `users.id` |
| `product_id` | CHAR(36) | FK 语义 → `products.id` |
| `first_viewed_at` | DATETIME | 首次 INSERT 写入，不更新 |
| `last_viewed_at` | DATETIME | 每次有效 POST（含 debounce 更新）刷新 |
| `view_count` | INT | 间断重置累计，默认 1 |

约束：`UNIQUE(user_id, product_id)`。索引：`ix_user_browse_history_user_id_last_viewed`（`(user_id, last_viewed_at)` ASC，列表排序；MySQL 反向扫描等效 DESC，且 Alembic autogenerate 可正常比对——2026-08-03 用户拍板由 DESC 改 ASC）。

migration：新 revision（如 `010_engagement_browse.py`），`down_revision` = 当前 head（`009_engagement_favorites`）。

### 3. API（JWT 隐式用户）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/browse` | `{ "product_id" }` → **202** `{ "accepted": true }` |
| GET | `/browse` | `?limit=&offset=` 分页列表 |
| DELETE | `/browse/{product_id}` | 删除单条 |

**未来扩展**：关键词搜索用 `GET /browse?keyword=`（query），**不**占用 `/{product_id}` 路径（DELETE 已占用 UUID 槽位）。

### 4. HTTP 状态码

| 场景 | 码 |
|------|-----|
| 未认证 | 401 |
| POST 受理（含 debounce no-op 计数） | **202** |
| POST 商品不存在 | 422 |
| DELETE 成功 | 204 |
| DELETE 无记录 | 404 |

### 5. POST /browse：校验 + BackgroundTasks

**同步路径（router）：**

1. JWT 解析 `user_id`
2. `catalog.service.get_products_for_engagement([product_id])` 为空 → **422**
3. `background_tasks.add_task(browse_service.record_browse_async, ...)`
4. 返回 **202** `{ "accepted": true }`

**异步路径（BackgroundTask / service）：**

```text
若 row 不存在：
  INSERT first_viewed_at=last_viewed_at=now, view_count=1

若 row 存在：
  gap = now - row.last_viewed_at
  若 gap <= DEBOUNCE_SECONDS：
    UPDATE last_viewed_at=now（view_count 不变）
  否则若 gap > RETENTION timedelta：
    UPDATE last_viewed_at=now, view_count=1（间断重置）
  否则：
    UPDATE last_viewed_at=now, view_count=view_count+1
  commit
```

**不在 POST 路径裁剪 top N**（由 trim job 负责）。

**会话与时间基准（2026-08-03 实现验证）：**
- `record_browse_async` 复用请求级 session（非独立 session）——测试经 SAVEPOINT override 使 HTTP 共享 db_session，独立 session 写库会因 REPEATABLE READ 快照不可见；且 FastAPI 0.139 实证 **background task 先于 dependency teardown 运行**（session 未关闭），生产同样安全。
- `now` 取 **UTC 墙钟 naive**（`datetime.now(UTC).replace(tzinfo=None)`）——asyncmy 对 DATETIME 列必返 naive（aware 落库亦按 UTC 墙钟存），测试 seed 用 `datetime.now(UTC)`；本地 CST(+8) 若用 `datetime.now()` 会差 8h 致 debounce/retention 误判。已实证 gap 计算正确。

**替代方案（未采用）：** 同步写 + 200 — 简单但 ADR/演进需 202 语义对接 Outbox；Outbox 本 change 不做。

### 6. view_count 语义：间断重置累计

- 连续活跃（间隔 `<= 30×24h`）：`view_count` 累加
- 间隔 `> 30×24h` 后再看：重置为 1（非滑动窗口内总次数）
- `first_viewed_at` 保留终身首次时间，供长期画像；`view_count==1` 仅表示当前活跃段起始

### 7. GET /browse：items + unavailable_items

与收藏 `_classify_favorites` 同源，抽 `BrowseService._classify_browses`：

1. 分页读 `user_browse_history`，按 `last_viewed_at DESC`
2. 批量 `get_products_for_engagement(product_ids)`
3. 分类 → `items` / `unavailable_items`（reason 枚举同收藏）

**BrowseItem（items）：** `id`, `product_id`, `first_viewed_at`, `last_viewed_at`, `view_count` — **不含** product 详情。

**UnavailableBrowseItem：** 上列 + `reason` + `product_name` + `image_url`。

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

`total` = 该用户全部 browse 行数（含 unavailable）。

### 8. DELETE /browse/{product_id}

对齐收藏：存在且属当前用户 → **204**；不存在 → **404**。

### 9. 配置（infra）

`app/infra/config.py` 新增：

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `BROWSE_HISTORY_MAX_PER_USER` | 50 | 每用户保留最近 N 条（trim） |
| `BROWSE_HISTORY_RETENTION_DAYS` | 30 | retention 天数（`timedelta(days=N)`） |
| `BROWSE_DEBOUNCE_SECONDS` | 5 | debounce 窗口 |

`.env.example`：50 / 30 / 5。`.env.test`：3（或 5）/ 30 / 5 — trim 单测用小 N，避免插 50+ 行。

### 10. Trim job

**模块：** `app/engagement/jobs/trim_browse_history.py`

**算法（按 user_id 分组）：**

1. 取该用户全部行，按 `last_viewed_at DESC`
2. top `MAX_PER_USER` 行 → 保留（无论是否超 retention）
3. 其余行中，`last_viewed_at < now - retention` → DELETE

**CLI：** `Taskfile.yml` 新增 `browse:trim` → `uv run python -m app.engagement.jobs.trim_browse_history`

**部署：** 生产由 **cron 独立进程** 定时执行（非 HTTP worker）；本地手动；CI 跑 unit 测试。

### 11. catalog 跨域（只读消费）

复用既有 `ShopService.get_products_for_engagement` → `EngagementProduct`；本 change **不修改** catalog 代码。

### 12. 测试策略

| 层级 | 范围 |
|------|------|
| integration | `tests/engagement/test_browse_*.py`；POST 202、await background、GET 分类、DELETE、401/422/404 |
| unit | `tests/unit/engagement/test_trim_browse_history.py` — top N 内超 retention 保留、top N 外删除 |
| catalog | 无变更，不新增单测 |

**BackgroundTasks 测试：** 使用 Starlette/FastAPI 测试模式在 assert 前 flush pending background tasks（与项目 async client fixture 配合）。

### 13. 绿阶段接口松弛（TDD 纪律补充）

TDD 红绿隔离默认纪律：**绿阶段不得读 `tests/` 下任何文件**，实现必须从 spec/design 推导（防止写出"刚好通过测试"而非从规格推导的实现）。

**例外（本 change Task 4 触发，经用户拍板）**：当 spec/design 未定义测试期望的**接口**（函数名、签名、类型）时，允许绿阶段读取测试的**接口声明部分**——import 语句、类型/helper 定义、函数调用签名；**不得读取断言逻辑**——算法与行为仍须从 spec/design 推导。

**判定准则：**

| 情形 | 绿阶段处理 |
|------|-----------|
| 接口可从 spec/design 推导 | 不读测试（默认） |
| 接口在 spec/design 缺项且无法推导 | 可读接口声明（imports/类型/调用签名），不可读断言 |
| 超出接口范畴的行为细节缺失 | 暂停并交用户拍板 |

> 本 change 实例：`plan_browse_trim_deletes` / `BrowseTrimRow` 系红阶段测试发明、design 未定义的接口；经用户授权读取其 import 块与类型/调用签名后实现，算法仍依 design §10。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| BackgroundTasks 进程崩溃丢浏览 | 接受；Non-goals 标注；后续 Outbox |
| trim job 未部署导致表超 N | 文档 + cron 说明；单测覆盖算法 |
| debounce 内刷新页面不 +1 | 符合 spec；权重由 `last_viewed_at` 仍更新 |
| 202 后立刻 GET 可能看不到新记录 | 可接受；前端不依赖即时一致性 |
| `view_count` 长期活跃用户累加偏高 | 间断重置 + `first_viewed_at` 供 AI 阶段再归一化 |

## Migration Plan

1. `devbox run -- task db:up && devbox run -- task migrate`（新 migration）
2. 部署后 `/browse*` 可用；无 backfill
3. 生产配置 cron 执行 `task browse:trim`（可选，MVP 可手动）
4. 回滚：`alembic downgrade -1` + 移除 router 路由（无跨域数据依赖）

## Open Questions

- （无阻塞项）archive 后是否将 browse 与 favorites 合并为单一 `engagement` spec — 当前独立 `engagement-browse` capability。
