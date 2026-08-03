## Why

`engagement-favorites` 已交付用户收藏能力，但 **浏览行为数据** 仍缺失；该信号与 `order_items` 购买数据并列，是 ADR-009 规划的 AI 推荐主输入，也是 engagement 域 Phase 2 的剩余垂直切片。本 change 交付可演示的浏览记录（upsert + 分页历史 + 单删 + 定时 trim），为后续 AI 域与 Outbox 演进提供 MySQL 行为底座。

## What Changes

- 扩展 **engagement 域**：`user_browse_history` 表（新 migration，依赖当前 head）；`BrowseService` + repository + schemas；复用既有 `catalog.service.get_products_for_engagement`
- **浏览 API**（均需 Bearer 认证；URL 不含 `user_id`）：
  - `POST /browse` — body `{ "product_id" }`；catalog 行存在即可；**202 Accepted** `{ "accepted": true }`；写库经 **BackgroundTasks** 异步 upsert
  - `GET /browse` — 分页列表；`items` + `unavailable_items`；按 `last_viewed_at` 降序
  - `DELETE /browse/{product_id}` — 删除单条浏览记录（误触清理）
- **浏览语义**：`(user_id, product_id)` upsert；`first_viewed_at`（首次 INSERT）、`last_viewed_at`（每次更新）、`view_count`（**间断重置累计**：距上次查看 `> 30×24h` 置 1，否则 +1）；debounce：`<= 5s` 内重复 POST 仅更新 `last_viewed_at`，不 +1
- **配置**（`app/infra/config.py` + `.env.example` / `.env.test`）：`BROWSE_HISTORY_MAX_PER_USER`（默认 50，test 3–5）、`BROWSE_HISTORY_RETENTION_DAYS`（30）、`BROWSE_DEBOUNCE_SECONDS`（5）
- **定时 trim**：`task browse:trim` CLI + unit 测试；删除「非 top N 且 `last_viewed_at` 超过 retention」的行；进 CI
- 扩展 **pytest**：`tests/engagement/` 集成测（await BackgroundTasks 后再 assert DB）；`tests/unit/engagement/` trim 单测
- 更新 **docs/architecture.md**（engagement 浏览部分）

## Non-goals

- 不实现 Outbox / Celery / at-least-once 持久化（BackgroundTasks 失败可静默丢失，留待后续 change）
- 不实现 AI Tool / 推荐 API / 专用 AI service 方法
- 不实现全量 event log（`browse_event_log` append-only）
- 不实现 `POST /browse/batch-delete`、关键词搜索（未来可用 `GET /browse?keyword=`）
- 不修改 catalog 公开 API 404 语义
- 不新增 catalog HTTP 路由或 DTO 变更（复用 `EngagementProduct`）
- 不实现未登录 / 匿名浏览埋点
- 不在 POST 路径同步裁剪 top N（仅 trim job 负责）

## Capabilities

### New Capabilities

- `engagement-browse`：用户商品浏览记录 upsert（202 + BackgroundTasks）、分页历史（items + unavailable_items）、单删、配置化 top N + retention trim job

### Modified Capabilities

- （无）— catalog `get_products_for_engagement` 已存在，本 change 仅消费

## Impact

- **业务域**：`engagement`（扩展）；`infra`（config）；`catalog`（只读消费，无 REST 变更）
- **跨域**：engagement → `catalog.service.get_products_for_engagement` + `EngagementProduct`
- **新增/修改**：`app/engagement/*`、新 migration、`app/infra/config.py`、`Taskfile.yml`（`browse:trim`）、`.env.example` / `.env.test`、`tests/engagement/`、`tests/unit/engagement/`、`docs/architecture.md`
- **API**：新增 `/browse*`；现有 API 不变
- **分支**：基于 `dev` 的 `feature/engagement-browse`
