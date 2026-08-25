# 项目架构设计

> 本文档描述 AI 赋能电商后端服务的整体架构。详细的设计决策见 [docs/decision/](./decision/)（ADR）；内部笔记见 [docs/notes/](./notes/)。

## 1. 项目概述

本项目是一个 **AI 赋能的电商平台**。核心思路是：**以传统电商业务为底座，在其上叠加 AI 能力**，而非从零做一个纯 AI 应用。

- **当前阶段（v1.0.0 底座）**：**user**（手机号 + SMS OTP 认证、JWT、资料/头像 attach）、**catalog**（店铺 + 类目/商品 + logo/主图 attach）、**ordering**（买家/卖家订单、购物车 checkout/batch-pay、支付桩与履约）、**engagement**（收藏、浏览足迹 + trim job）、**support**（店铺客服会话、inbox、product ref）、**media**（上传/下载/删除、FK attach + URL resolve）与 **infra** 横切能力均已交付；Alembic 至 migration `015`；全量 pytest **480 项**
- **演进方式**：垂直切片增量交付，SDD + TDD，CI 从第一天启用；v1.x 完善 CD（`infra-cd-compose`），v2.0.0 进入 AI 阶段
- **预估规模**：`app/` 约 7500 行，全项目约 1 万行（含 tests）

## 2. 技术栈

| 层次 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 业务 API 与 AI API 统一入口 |
| 业务数据库 | MySQL | 唯一真实数据源（Single Source of Truth） |
| ORM / 迁移 | SQLAlchemy + Alembic | 初期仅 business 迁移入口 |
| AI 框架（后期） | LangChain / LangGraph / DeepAgents | 按功能分模块引入 |
| 向量数据库（AI 读库） | PostgreSQL + pgvector | infra 已接入（`ai_database`/`alembic_ai`/`embedder`）；业务 RAG 检索后期 |
| 工程规范 | OpenSpec (SDD) + pytest (TDD) + CI | 详见工程约定 |

## 3. 架构总览：二维结构

系统采用 **「业务域（纵切）× 平台能力（横切）」** 的二维架构：

```text
                    ┌─────────────────────────────────────┐
                    │         路由 / 编排层               │
                    │   HTTP（前端功能级）+ 后端 agent 意图 │
                    └──────────┬──────────────┬───────────┘
                               │              │
          ┌────────────────────┼──────────────┼────────────────────┐
          │  纵轴：业务域       │              │  邻接：AI 能力域    │
          │                    ▼              ▼                    │
          │  ┌──────────┐ ┌──────────┐ ┌──────────┐  ┌──────────┐ │
          │  │   user   │ │ catalog  │ │ ordering │  │    ai    │ │
          │  │ 用户认证  │ │ 商品目录  │ │ 订单购物车│  │ RAG/推荐 │ │
          │  └──────────┘ └──────────┘ └──────────┘  │ 助手/搭子 │ │
          │  ┌──────────┐ ┌──────────┐                  └────┬─────┘ │
          │  │engagement│ │ support  │                        │       │
          │  │收藏/浏览  │ │店铺客服   │◄───────────────────────┘       │
          │  └──────────┘ └──────────┘         Tool 调用业务 service   │
          └────────────────────────────┬─────────────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │  横轴：平台能力（infra / events）      │
                    │  配置、DB Session、JWT、Outbox（后期）  │
                    └─────────────────────────────────────┘
```

### 3.1 纵轴：业务域（限界上下文）

每个业务域是一个 **限界上下文（Bounded Context）**，内部采用 router → service → repository → model 分层：

| 域 | 职责 | 核心实体 | 阶段 |
|----|------|----------|------|
| `user` | 注册、登录、JWT、用户资料、`is_admin`（不对外暴露） | User | **MVP（已实现）** |
| `catalog` | 店铺（shop）、平台类目树、商品 CRUD/上下架 | Shop, Category, Product, ProductCategory | **MVP（已实现）** |
| `ordering` | 买家/卖家订单、购物车、checkout 分组、库存预留/释放、支付桩、发货与确认收货 | Order, OrderItem, CartItem, CheckoutBatch | **已实现** |
| `engagement` | 用户收藏、浏览记录（upsert + 分页历史 + 单删 + 定时 trim） | UserFavorite、UserBrowseHistory | **已实现** |
| `support` | 店铺客服会话（shop 管辖、lazy create、inbox、product ref；预留 AI） | SupportConversation、SupportMessage | **已实现** |
| `media` | 媒体文件上传/下载/删除、**业务 attach（`*_media_id` FK + mark_public）**、元数据查询、所有权与可见性控制、本地存储抽象（双 backend） | MediaAsset | **已实现**（见 [media-storage spec](../../openspec/specs/media-storage/spec.md)） |
| `ai` | RAG、推荐、经营助手、购物搭子 | — | AI 阶段 |

### 3.2 邻接：AI 能力域

AI **不是** 横切进每个业务域的内部，而是与业务域 **并列** 的独立能力域：

- Agent 通过 **Tool** 调用各业务域的 **service**，不直连 repository 或 ORM
- RAG 检索读 PostgreSQL 向量副本，强一致数据（库存、价格、订单状态）走 Tool 实时查 MySQL
- **前端**只做功能级路由（进 AI 客服 vs 人工 support vs 经营助手）；**消息级意图**留在后端 agent（NLU），见 [ADR-013](./decision/ADR-013-AI域组合根与消费边界.md)
- RAG 是叶子库（无 HTTP）；组合根为 `app/ai/deps.py` 装配类。业务域 **SHALL NOT** import `app.ai`

### 3.3 横轴：平台能力

| 模块 | 职责 |
|------|------|
| `infra/` | 配置、数据库 Session、**Redis 客户端**、**PostgreSQL AI 读库（`ai_database` + `embedder`）**、JWT、健康/readiness 探针（三库聚合）、**结构化日志**、**统一 error JSON**、**分页（已实现）**|
| `events/`（后期） | Outbox、领域事件，驱动 MySQL → pgvector **防腐层**同步（异构库，非查询过滤） |
| `shared/`（可选） | 无业务含义的公共类型，保持极简 |

## 4. 域间协作规则

### 4.1 依赖方向

```text
✓ 跨域：ordering.service → catalog.service → 返回 schema（DTO）
✓ 域内：router → service → repository → ORM model
✓ AI：ai.tools / indexing / retrieval → 各域 service + schema；AI `deps.py` 可取业务域 service-provider
✓ 各域 → infra

✗ 跨域 import 对方的 ORM model 或 repository
✗ 业务域 import ai（含 service / schemas / deps，与 ADR-010 业务域互取不对称，见 ADR-013）
✗ AI service 自装配别域 deps（接线只在 `app/ai/deps.py`）
✗ infra import 任何业务域
```

### 4.2 数据传输

- **跨域边界**：使用 Pydantic schema 作为 DTO（如 `ProductSummary`、`UserSummary`）
- **ORM 所有权**：谁拥有表，谁拥有 ORM；对外只暴露 service + schema
- **API 层**：router 使用本域 schemas 做请求校验与响应序列化

### 4.3 读写路径

| 路径 | 策略 |
|------|------|
| **写操作**（下单、扣库存、收藏） | 严格跨域 service 调用 |
| **读操作**（列表、详情） | 域内可用 SQLAlchemy relationship；跨域只读字段可在本域 `queries.py` 中 JOIN，返回 schema，不暴露 foreign ORM |

### 4.4 同进程性能说明

单体阶段跨域 service 调用是函数调用 + 若干 SQL，性能影响可忽略。边界清晰带来的可维护性优先于 JOIN 便利。

### 4.5 应用层边界纪律（deps / service / router）

分层：router（HTTP）→ deps（装配 + 请求上下文解析）→ service（业务）→ repository → ORM。

**deps = 组合根：装配自由 + 无副作用**

- 两大类：**装配类**（`get_*_repository` / `get_*_service`）+ **解析类**（`get_current_*`，鉴权 + 实体解析，**只被本域 router 消费**）。
- 无副作用：只做注入 + 存在性定位（404）+ 状态无关的归属比较；不触发写、不建 schema、不做业务数据准备。
- **current-object 解析判据（三分类）**：
  - **纯读解析**（查实体 + 404 + 归属比较，无副作用）→ 本域仓储直读（`get_current_shop` / `get_current_product` / `get_current_cart_item` / `get_current_checkout_batch` / `get_current_user`）
  - **业务读**（解析伴随副作用，如 ordering 懒释放）→ deps 纯定位 + service 读方法内完成（`get_current_order` → `get_order_response(order)`）
  - **跨域解析**（本域 deps 解析别域实体）→ 对方 service 公开方法（schema），deps 只转发不建 schema（support `get_current_support_shop` 转发 `get_my_shop_context`）
- 鉴权切分：状态无关（buyer/owner/user 比较）→ deps；状态依赖（过期 / 可支付 / 店铺关闭）→ service 方法内。

**service = 业务逻辑 + schema 权威出口**

- 公开方法仅两类：返 schema（跨域/响应）+ 业务方法（含业务读）。**不为 deps 造返 ORM 公开 getter**（`get_shop_or_404` 不新增、`get_order_or_404` 私有化）。
- 方法自含业务完整性（不依赖调用方/deps 先触发业务前置，cancel 补 expire 为模板）；被跨模块/跨域消费的方法不得私有。

**router = 薄**

- 拿 deps 实体必须传 service 方法，**不得直接序列化**（deps 只保证"存在 + 有权"，不保证"新鲜 + 完整"）。
- 错误语义：归属失败统一 404（不泄漏存在性）；状态失败 409/422（service 内）。

**AI 组合根（相对 ADR-010 不对称，见 [ADR-013](./decision/ADR-013-AI域组合根与消费边界.md)）**

- 落点：`app/ai/deps.py` 仅装配类；CLI / 测试当普通函数调用，有 AI router 后再 `Depends` 同一函数。
- 无 AI HTTP 时不建空 router、不写 `get_current_*`。indexing 的 `MediaService` 必传，service 不得 import `app.media.deps`。

> 完整纪律与铁律见 [ADR-010](./decision/ADR-010-应用层边界纪律.md)、[ADR-013](./decision/ADR-013-AI域组合根与消费边界.md) 与 `.cursor/rules/app-layer-discipline.mdc`。

## 5. 目录结构

### 5.1 当前骨架（user + catalog + ordering + engagement + support + infra）

```text
e-commerce-system/
├── app/
│   ├── main.py                   # create_app() 工厂：logging → middleware → handlers → 路由
│   ├── infra/
│   │   ├── config.py             # DATABASE_URL、REDIS_URL、AI_DATABASE_URL、EMBEDDING_*、APP_ENV、jwt_*、sms_*、ORDER_RESERVATION_TTL_SECONDS
│   │   ├── database.py           # async engine、AsyncSession、Base、get_db、reset_engine
│   │   ├── ai_database.py        # AI 读库 async engine、AiBase、get_ai_engine/get_ai_session_factory/reset_ai_engine
│   │   ├── embedder.py           # Embedder 协议、MockEmbedder、厂商骨架、get_embedder、启动维度校验
│   │   ├── redis.py              # redis.asyncio 连接池、get_redis、reset_redis
│   │   ├── auth.py               # PyJWT、OAuth2PasswordBearer、get_current_user_id
│   │   ├── logging/              # loguru setup、InterceptHandler、RequestIDMiddleware
│   │   ├── errors/               # 全局 exception handlers、统一 error JSON
│   │   ├── health/               # 存活探针 GET /health
│   │   ├── readiness/            # 就绪探针 GET /health/ready（MySQL + Redis + PostgreSQL 检查）
│   │   ├── pagination/           # 分页基础设施（PaginationParams、get_pagination_params、Paginated[TResponse]）
│   │   └── models/               # infra 验证用 ORM（_infra_migration_smoke、_infra_ai_migration_smoke）
│   ├── user/                     # 用户域（router → service → repository → model）
│   │   ├── router.py             # POST /auth/sms/*、/auth/login，GET/PATCH /users/me
│   │   ├── service.py            # SMS 注册/登录、密码登录、资料更新
│   │   ├── sms_service.py        # Redis OTP（send/consume/verify_fail 限流）
│   │   ├── phone.py              # 手机号规范化
│   │   ├── repository.py
│   │   ├── models.py             # users 表（phone 唯一、email 可空、含 is_admin）
│   │   ├── schemas.py
│   │   └── deps.py               # get_current_user、require_admin、SmsOtpService
│   ├── catalog/                  # 商品目录域（shop + 类目/商品 + 库存预留/释放）
│   │   ├── router.py             # categories/products/shops 路由
│   │   ├── service.py            # 类目、商品、店铺、可购查询、reserve/release_stock
│   │   ├── repository.py
│   │   ├── models.py             # shops、categories、products、product_categories
│   │   ├── schemas.py            # 含 PurchasableProduct 等跨域 DTO
│   │   └── deps.py               # get_current_shop
│   └── ordering/                 # 订单域（买家订单 + 购物车）
│       ├── router.py             # POST/GET /orders、pay/shipments/confirm-receipt/cancel、batch-pay、GET /shops/me/orders
│       ├── cart_router.py        # /cart*、GET /orders/checkout-batches/{id}
│       ├── service.py            # 建单、懒释放、batch_pay_orders
│       ├── cart_service.py       # Cart CRUD、list enrichment、checkout 编排
│       ├── cart_repository.py
│       ├── checkout_batch_repository.py
│       ├── repository.py
│       ├── models.py             # orders、order_items、cart_items、checkout_batches
│       ├── schemas.py
│       └── deps.py
│   └── engagement/               # 用户行为域（收藏 + 浏览已实现）
│       ├── router.py             # POST/GET/DELETE /favorites*、POST /favorites/batch-delete；POST/GET /browse、DELETE /browse/{product_id}
│       ├── service.py            # FavoriteService；BrowseService（record_browse_async 异步 upsert、列表分类、单删）
│       ├── repository.py
│       ├── models.py             # user_favorites、user_browse_history
│       ├── schemas.py
│       ├── deps.py
│       └── jobs/                 # trim_browse_history.py（task browse:trim，top N + retention 裁剪）
│   └── support/                  # 店铺客服域（会话 + 消息已实现）
│       ├── router.py             # 买家 /support/shops/{shop_id}/*；店主 /support/inbox/*
│       ├── service.py            # lazy create、inbox、closed/禁自购/403404 规则
│       ├── repository.py
│       ├── models.py             # support_conversations、support_messages
│       ├── schemas.py
│       └── deps.py
│   └── media/                    # 媒体平台域（上传/下载/删除/attach 已实现，见 media-storage spec）
│       ├── router.py             # POST /media、GET /media/{id}（元数据）、GET /media/{id}/file、DELETE /media/{id}（引用 409）
│       ├── service.py            # upload、delete、get_file_stream、can_read、get_detail、assert_owned_by、assert_image_content_type、mark_public、resolve_urls、count_references
│       ├── repository.py         # MediaRepository（insert/get_by_id/get_many_by_ids/count_references/delete_by_id）
│       ├── models.py             # media_assets（8 列）
│       ├── schemas.py            # MediaSummary、MediaDetail
│       ├── deps.py               # get_storage_backend、get_media_service
│       ├── rate_limit.py         # Redis 固定窗口上传限速
│       ├── validation.py         # 魔数检测 + MIME 白名单 + 大小校验
│       └── storage/
│           ├── protocol.py       # StorageBackend 协议
│           ├── local.py          # LocalFilesystemBackend（落盘）
│           └── memory.py         # InMemoryBackend（进程内，测试用）
├── alembic/
│   └── versions/
│       ├── 001_create_infra_migration_smoke.py
│       ├── 002_create_users.py
│       ├── 003_catalog_shop.py   # users.is_admin + shops 表 + seed 管理员
│       ├── 004_catalog_products.py  # categories、products、product_categories（无 seed）
│       ├── 0ca23eb664a9_005_ordering_orders.py  # orders、order_items
│       ├── e1674055eb99_006_ordering_initiated_by.py  # orders.initiated_by
│       ├── ece9a7855313_007_ordering_cart.py  # cart_items、checkout_batches、orders.checkout_batch_id
│       ├── 008_user_phone.py     # users.phone 唯一、email/password_hash 可空、admin phone 回填
│       ├── 009_engagement_favorites.py  # user_favorites
│       ├── 010_engagement_browse.py     # user_browse_history
│       ├── 011_support_conversations.py # support_conversations、support_messages
│       ├── b4fffd14db3c_012_media_assets.py  # media_assets
│       └── 25a1017514aa_013_media_attach_fk.py  # avatar/logo/primary_media_id FK
├── alembic_ai/                  # AI 读库独立 Alembic 入口（alembic_ai.ini；仅管 PostgreSQL schema）
│   └── versions/
│       └── 001_create_infra_ai_migration_smoke.py  # CREATE EXTENSION vector + _infra_ai_migration_smoke（vector(1024)）
├── tests/
│   ├── conftest.py               # httpx AsyncClient、reset_engine/reset_redis、Redis fixture、auth helper
│   ├── ops/                        # health、readiness、migration smoke
│   ├── infra/
│   │   ├── test_logging.py       # loguru、request_id、logs/app.log
│   │   ├── test_error_handlers.py # 统一 error JSON
│   │   ├── test_database.py      # AsyncSession 烟雾
│   │   └── test_redis.py         # REDIS_URL、PING、SET/GET/TTL
│   ├── user/                     # SMS/密码认证、me/profile integration
│   ├── catalog/                  # 店铺 + 类目/商品 + seed integration
│   ├── ordering/                 # 买家订单 + 购物车 integration
│   ├── engagement/               # 用户收藏 + 浏览 integration
│   ├── media/                     # media 域 integration（17 测例）
│   ├── unit/
│   │   └── media/                  # media 域单元测试（29 测例）
│   └── support/                  # 店铺客服会话 integration
├── scripts/                      # devbox 三库运维（scripts/devbox/）、Allure 打开报告、test-import 检查（无 curl 烟雾脚本）
│   ├── devbox/                   # 监督器共享 services + db 总闸 + mysql/redis/pg 分库 up/down/reset
│   ├── allure_open_report.sh     # Task latest:report
│   ├── check_no_test_cross_imports.sh  # Task check-test-imports；依赖 rg（ripgrep），见 test-architecture / infra-ci spec
│   └── check_app_layer_discipline.py   # Task check-app-layer-discipline（AST 边界纪律）
├── .github/workflows/test.yaml       # Run Tests：paths-filter、lint、单 job task test
├── .github/workflows/build-push.yaml # Build and Push Container Images：tag-only GHCR
└── ...
```

**应用入口（`create_app`）**：按序组装 `setup_logging(settings)` → `RequestIDMiddleware`（纯 ASGI，`X-Request-ID` 透传/生成）→ `register_exception_handlers(app)` → 各域 router。错误响应统一为 `{"error": {"code", "message", "request_id"}}`（详见 `infra-api-errors` spec）。日志经 loguru 输出至 stderr 与 `logs/app.log`（development/production；test 仅 stderr 且 level=WARNING）。详见 [中间件栈与异常处理架构决策（ADR-004）](./decision/ADR-004-中间件栈与异常处理架构决策.md)。

**`users` 表（user 域）**：`id`（UUID PK，JWT `sub` 锚点）、`phone`（VARCHAR 20，UNIQUE，业务主标识）、`email`（可空，仅资料）、`password_hash`（可空，SMS 注册用户须设密码）、`nickname`、`is_active`、`is_admin`（不对外暴露）、`avatar_media_id`（可空 FK → `media_assets.id`，attach 头像后写；响应 resolve 为 `avatar_url`）、`created_at`、`updated_at`。SMS OTP 存 Redis（`sms:otp:{phone}`、`sms:verify_fail:{phone}`、`sms:daily:{phone}:{date}`），见 `user/sms_service.py`。

**`shops` 表（catalog 域）**：`id`（UUID PK）、`owner_user_id`（FK → `users.id`，UNIQUE，当前一用户一店）、`name`（UNIQUE）、`description`、`logo_media_id`（可空 FK → `media_assets.id`；响应 resolve 为 `logo_url`）、`status`（`active` | `closed`）、`created_at`、`updated_at`。跨域仅通过 `infra.auth.get_current_user_id` 解析 JWT，不在 `User` ORM 上声明跨域 relationship。

**`categories` 表（catalog 域）**：`id`（UUID PK）、`parent_id`（FK → `categories.id`，NULL 为根）、`name`（VARCHAR 64）、`created_at`、`updated_at`；`UNIQUE(parent_id, name)` 同级不重名；**无 seed**，空库起步。

**`products` 表（catalog 域）**：`id`（UUID PK）、`shop_id`（FK → `shops.id`）、`name`、`description`、`price`（DECIMAL 10,2，CNY）、`stock`、`is_published`（默认 false）、`primary_media_id`（可空 FK → `media_assets.id`，主图；响应 resolve 为 `image_url`）、`created_at`、`updated_at`；索引 `ix_products_shop_id`、`ix_products_is_published`。

**`product_categories` 表（catalog 域）**：`(product_id, category_id)` 复合 PK、`is_primary`（BOOLEAN）；service 保证每个商品至多一个主类目；`primary_category_id` 必须 ∈ `category_ids`。

**`orders` 表（ordering 域）**：`id`（UUID PK）、`buyer_user_id`（FK 语义 → `users.id`）、`shop_id`（FK 语义 → `shops.id`）、`status`（`awaiting_payment` | `confirmed` | `shipped` | `completed` | `cancelled`）、`cancel_reason`（可空）、`total_amount`（DECIMAL 12,2）、`expires_at`（待支付预留截止）、`initiated_by`（`buyer` | `seller`）、`checkout_batch_id`（可空 FK → `checkout_batches.id`；立即购买为 NULL）、`created_at`、`updated_at`；索引含 `ix_orders_buyer_user_id`、`ix_orders_shop_id`、`ix_orders_status`、`ix_orders_expires_at`、`ix_orders_checkout_batch_id`。跨域仅存 FK 字段，**不**声明跨域 relationship。

**`order_items` 表（ordering 域）**：`id`（UUID PK）、`order_id`（FK → `orders.id`）、`product_id`（快照关联）、`product_name`、`unit_price`（DECIMAL 10,2）、`qty`（> 0）。创建时写入价格与商品名快照；1 订单 = 1 店 + 多行。

**`cart_items` 表（ordering 域）**：`id`（UUID PK）、`user_id`（FK → `users.id`）、`product_id`（仅存 ID，展示走 catalog.service）、`qty`（> 0）、`created_at`、`updated_at`；`UNIQUE(user_id, product_id)`；索引 `ix_cart_items_user_id`。暂存不占库存、不建单；**不**跨域 ORM relationship。

**`checkout_batches` 表（ordering 域）**：`id`（UUID PK）、`buyer_user_id`（FK → `users.id`）、`created_at`。轻量分组标签（无行项目/总价/status）；cart checkout 时创建，供 `GET /orders/checkout-batches/{id}` 层级展示；支付走通用 `POST /orders/batch-pay`。

**库存预留（catalog ↔ ordering）**：创建订单时 ordering service 在同一事务内调用 catalog `reserve_stock`（条件 `UPDATE ... SET stock=stock-qty WHERE stock>=qty`）；取消或懒过期释放时调用 `release_stock`。cart checkout 在单事务内按店 split 多次建单（`_create_order_core(commit=False)`）后统一 commit。ordering **不得** import catalog ORM/repository。

**购物车读路径**：`GET /cart` 批量调用 `catalog.service.get_purchasable_products` enrichment，按店分组；不可购项进 `invalid_items`（不自动删除）。列表展示 catalog 实时价；成交价以 checkout 建单时 `order_items` 快照为准。

**`user_favorites` 表（engagement 域）**：`id`（UUID PK）、`user_id`（FK → `users.id`）、`product_id`（仅存 ID，展示走 catalog.service）、`created_at`；`UNIQUE(user_id, product_id)`；索引 `ix_user_favorites_user_id`。**不**存 price/name/image 快照；**不**跨域 ORM relationship。语义为**用户偏好**，与 ordering 域 `cart_items`（购买意图）独立。

**收藏读路径**：`GET /favorites` 分页读 `user_favorites` → 批量 `catalog.service.get_products_for_engagement` → 分类为 `items`（可公开展示；前端再调 `GET /products/{id}`）与 `unavailable_items`（含 `reason`：`product_unpublished` | `shop_closed` | `not_found`，及 `product_name`/`image_url` enrichment）。POST 收藏校验 catalog 行存在即可（不要求可购）。`POST /favorites/batch-delete` 接受 `{ "product_ids": [...] }`（对标 `POST /orders/batch-pay`）；engagement **不得** import catalog ORM/repository。catalog 跨域 DTO：`EngagementProduct` + `get_products_for_engagement`（与 `get_purchasable_products` 共用 repository 批量 SQL）。

**`user_browse_history` 表（engagement 域）**：`id`（UUID PK）、`user_id`（FK → `users.id`）、`product_id`（仅存 ID，展示走 catalog.service）、`first_viewed_at`（首次 INSERT，不更新）、`last_viewed_at`（每次有效 POST 刷新）、`view_count`（INT，间断重置累计）；`UNIQUE(user_id, product_id)`；索引 `ix_user_browse_history_user_id_last_viewed`（`(user_id, last_viewed_at)` ASC，MySQL 反向扫描等效 DESC）。**不**存 price/name/image 快照；**不**跨域 ORM relationship。语义为**近期足迹 + 兴趣强度**，与 `user_favorites`（长期偏好）独立。

**浏览写路径（`POST /browse`）**：认证用户提交 `{ "product_id" }` → catalog 校验（不存在 → 422 且不调度）→ **202** `{ "accepted": true }` + **BackgroundTasks** 异步 upsert（`BrowseService.record_browse_async`，复用请求级 session）。upsert 语义：首次 INSERT `view_count=1`；debounce（`<= BROWSE_DEBOUNCE_SECONDS`）仅刷 `last_viewed_at` 不 +1；间断重置（距上次 `> BROWSE_HISTORY_RETENTION_DAYS`）`view_count` 归 1；活跃期 +1。`first_viewed_at` 终身不变。时间基准用 UTC 墙钟 naive（`datetime.now(UTC).replace(tzinfo=None)`），与 asyncmy 对 `DATETIME` 的 naive 读回一致。

**浏览读路径（`GET /browse`）**：分页读 `user_browse_history`（`last_viewed_at DESC`）→ 批量 `get_products_for_engagement` → 分类为 `items`（可展示；不含嵌套 product 详情）与 `unavailable_items`（`reason`：`product_unpublished` | `shop_closed` | `not_found`，含 `product_name`/`image_url` enrichment）；`total` 计该用户全部 browse 行（含 unavailable）。`GET /browse` **不**自动删除 unavailable 行（用户 `DELETE /browse/{product_id}` 主动清理；204 / 404）。

**定时 trim（`task browse:trim`）**：`app/engagement/jobs/trim_browse_history.py`，生产由 **cron 独立进程** 定时执行（非 HTTP worker）。算法：每用户按 `last_viewed_at DESC` 取 top `BROWSE_HISTORY_MAX_PER_USER` 保留（top N 内行即使超 retention 也保留）；其余行中 `last_viewed_at < now - BROWSE_HISTORY_RETENTION_DAYS` 删除。纯函数 `plan_browse_trim_deletes`（`BrowseTrimRow` 输入、返回应删行 id 集合）可单测；`__main__` 供 `task browse:trim` CLI。

**`support_conversations` 表（support 域）**：`id`（UUID PK）、`shop_id`（FK 语义 → `shops.id`）、`buyer_user_id`（FK 语义 → `users.id`）、`handler_mode`（`ai` \| `human`，**默认 `ai`**；前端 PATCH 切换，`human` 时人工模式不进 NLU）、`last_message_preview`（VARCHAR 200）、`created_at`、`updated_at`；`UNIQUE(shop_id, buyer_user_id)`（一买家一店一会话）；索引 `ix_support_conversations_shop_updated`（`(shop_id, updated_at)` 供 inbox 降序）。**不**跨域 ORM relationship。演进对齐 [ADR-007](./decision/ADR-007-多租户扩展-设计与暂缓计划.md)：隔离键 `shop_id`；演示阶段店主兼客服（`ShopService.get_my_shop` 自解析）。

**`support_messages` 表（support 域）**：`id`（UUID PK）、`conversation_id`（FK → `support_conversations.id`）、`sender_role`（`buyer` \| `shop`）、`author_role`（`human` \| `ai`；买家/店主人工消息为 `human`，AI 回合助手消息为 `ai`）、`body`（TEXT 可空）、`message_refs`（JSON 可空，`[{ref_type, ref_id}]`，MVP 仅 `product`）、`created_at`；索引 `ix_support_messages_conversation_created`（`(conversation_id, created_at)` ASC 供历史）。`body` 与 `message_refs` 至少一项非空。

**support 写路径（买家 `POST /support/shops/{shop_id}/conversation/messages`）**：JWT 买家 → `ShopService.get_shop_context`（不存在 404）→ 禁自购（`buyer == owner_user_id` → **403**）→ closed 店任意 POST → **422** → 校验 body/refs（空/超长/ order ref / refs>10 → 422）→ `validate_product_refs_for_shop` → lazy create 或追加消息（默认 `handler_mode=ai`）→ 若为 AI 模式：**同步调 AI Port**（`main.py` 注册的 `build_buyer_turn_handler` 工厂）生成助手消息（`author_role=ai` / `sender_role=shop`），preview 更新为助手正文截断；Port 未注入 / 失败 → 兜底转人工文案，买家 POST 仍 201。**响应体始终是买家那条消息**（助手消息经随后 GET messages 可见）。

**support 模式切换（买家 `PATCH /support/shops/{shop_id}/conversation`）**：仅会话买家可改本店该会话 `handler_mode`（`ai` \| `human`）；成功 200 + ConversationResponse；无会话 404；非法枚举 422；未认证 401。NLU / AI Port **不**调用此接口、不直接写 `handler_mode`。

**support 读路径（买家）**：`GET .../conversation` 有会话 200 / 无 404；`GET .../messages` 分页 ASC / 无会话 404。非 buyer 且非店主 → **404**。

**support 店主路径（`GET /support/inbox*`、`POST .../inbox/{id}/messages`）**：`ShopService.get_my_shop` 鉴权（service 内自解析）；inbox 按 `updated_at DESC` 含 `last_message_preview`；非本店会话 404；closed 店仍允许回复已有会话。support **不得** import catalog / ordering ORM；商品校验走 `ShopContext` + `validate_product_refs_for_shop`（catalog service，见 `catalog-products` spec）。

**`media_assets` 表（media 域）**：`id`（UUID PK）、`owner_user_id`（FK → `users.id`）、`visibility`（`owner_only` | `public`，默认 `owner_only`）、`content_type`（魔数检测后的 MIME）、`size_bytes`、`storage_key`（两级分片路径 `{hex[:2]}/{hex[2:4]}/{hex}`）、`original_filename`（客户端上传名）、`created_at`。字节由 `StorageBackend` 管理（`LocalFilesystemBackend` 落盘 / `InMemoryBackend` 测试用）；API URL 用 `id` 而非 `storage_key`。上传校验链：`file.size` 预检（413）→ MIME 白名单 → 魔数检测 → 禁 SVG。限速：Redis 固定窗口每用户计数。media **不得** import 业务域 ORM/repository。

**attach（`media-attach` change 已交付）**：user/catalog 写路径存 `*_media_id` FK（`users.avatar_media_id` / `shops.logo_media_id` / `products.primary_media_id`）；attach 时 `assert_owned_by`（非本人 → 403）+ `assert_image_content_type`（非 `image/*` → 422，message 含 media_id）+ 同事务 `mark_public`；读路径 `resolve_urls(ids)` 批量把 FK 翻译为 `/media/{id}/file`，缺失行 → 对应 url 字段 `null`（列表批量防 N+1）；`GET /media/{id}` 返回 `MediaDetail` 元数据（读权限同 `/file`）；DELETE 前 `count_references` > 0 → 409（DB FK `ON DELETE RESTRICT` 为第二道保险）。URL 拼写规则仅存于 media 域；user/catalog 只调 `media.service` + schema，不 import media ORM/repository。见 [media-storage spec](../../openspec/specs/media-storage/spec.md)。

### 5.2 规划中的完整结构

随垂直切片增量补充后期的 `ai/`、`events/` 等。`user/`、`catalog/`、`ordering/`、`engagement/`、`support/`、`media/` 与 `infra/` 已按 router → service → repository → model + schemas 分层实现。

```text
app/
├── main.py                       # create_app()：setup_logging → middleware → handlers → routers
├── infra/
│   ├── health/                   # 已实现
│   ├── readiness/                # 已实现（MySQL + Redis + PostgreSQL 聚合检查）
│   ├── redis.py                  # 已实现（redis.asyncio、get_redis）
│   ├── logging/                  # 已实现（loguru、request_id、logs/app.log）
│   ├── errors/                   # 已实现（统一 error JSON、全局 handlers）
│   ├── config.py                 # 已实现（含 jwt_*、app_env、AI_DATABASE_URL、EMBEDDING_*）
│   ├── database.py               # 已实现
│   ├── ai_database.py            # 已实现（AI 读库 async engine、AiBase、get_ai_engine）
│   ├── embedder.py               # 已实现（Embedder 协议、MockEmbedder、get_embedder、维度校验）
│   ├── auth.py                   # 已实现
│   └── pagination/               # 已实现（PaginationParams、get_pagination_params、Paginated[TResponse]）
├── user/                         # 已实现（认证垂直切片）
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   └── deps.py
├── catalog/                      # MVP（shop + 类目/商品已实现）
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   └── deps.py
├── ordering/                     # MVP（买家路径 + 购物车已实现）
│   ├── router.py
│   ├── cart_router.py
│   ├── service.py
│   ├── cart_service.py
│   ├── cart_repository.py
│   ├── checkout_batch_repository.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   └── deps.py
├── engagement/                   # 收藏 + 浏览已实现
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   ├── deps.py
│   └── jobs/                     # trim_browse_history（task browse:trim）
├── support/                      # 店铺客服（会话 + inbox 已实现）
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   └── deps.py
├── media/                        # 媒体平台域（上传/下载/删除/attach 已实现）
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   ├── deps.py
│   ├── rate_limit.py
│   ├── validation.py
│   └── storage/
│       ├── protocol.py
│       ├── local.py
│       └── memory.py
├── events/                       # 后期
└── ai/                           # 后期
```

## 6. 电商 MVP 范围

### 6.1 包含

- 用户注册 / 登录（JWT）
- 商品 CRUD、类目、上下架
- 创建订单、查询订单、取消订单、支付桩、发货、确认收货
- 库存预留与释放（创建扣减、取消/超时加回；订单行快照价格与商品名）
- **购物车**（ordering 域）：`cart_items` 暂存、`POST /cart/checkout` 跨店单事务建单 + 轻量 `checkout_batches`、`POST /orders/batch-pay` 合并支付；与 `POST /orders` 立即购买并行
- **收藏**（engagement 域）：`user_favorites`；`POST/GET/DELETE /favorites*`、`POST /favorites/batch-delete`（用户偏好，与购物车语义独立）
- **浏览**（engagement 域）：`user_browse_history`；`POST/GET /browse`、`DELETE /browse/{product_id}`（202 异步 upsert、分页历史、单删）+ 配置化 top N + retention 定时 trim（`task browse:trim`，生产 cron 独立进程）
- **店铺客服**（support 域）：`support_conversations`、`support_messages`；买家 `GET/POST /support/shops/{shop_id}/conversation*`（lazy create、product ref、默认 AI + 买家 PATCH 切模式）；店主 `GET/POST /support/inbox*`（inbox、`last_message_preview`）；禁自购 403、closed 店买家 POST 422；AI 回合写 `author_role=ai`，**无** `/ai/*` 路由（AI 经 support Port 同步调用）

### 6.2 明确不做（MVP）

| 模块 | 原因 |
|------|------|
| 支付 | 流程长、合规多，对 AI 赋能价值低 |
| 物流 | 同上 |
| 优惠券 / 促销 | 复杂度高，非 AI 核心素材 |
| 多店铺 / 多租户 | 单店 MVP 足够 |
| SKU 多规格 | 一个 product = 一个 SKU，后期再扩展 |

### 6.3 订单状态（买家路径）

```text
awaiting_payment ──pay──▶ confirmed ──shipments──▶ shipped ──confirm-receipt──▶ completed
       │                      │                      │
       └──────── cancel / lazy-expire ───────────────┘
                         ▼
                    cancelled
```

- 创建订单时**预留库存**（非直接进 confirmed）；`expires_at = now + ORDER_RESERVATION_TTL_SECONDS`（默认 86400 秒）
- **懒释放**：读单、支付等路径检查过期 → `cancelled` + `cancel_reason=expired` 并释放库存（无 Redis/MQ/周期扫描）
- 支付为**桩**（无外部渠道）；非法状态迁移 → **409**；跨店/超卖/未上架 → **422**；禁自购 → **403**

### 6.4 购物车与结算（买家路径）

```text
加购（cart_items，实时价展示）
       │
       ▼
POST /cart/checkout（部分 cart_item_ids，单事务）
  · 创建 checkout_batch + 按店 N 个 awaiting_payment 子单（快照锁价）
  · 删除已结算 cart 行
       │
       ▼
POST /orders/batch-pay（通用；可子集、可跨 batch）
       │
       ▼
confirmed → shipped → completed（与立即购买相同履约路径）
```

- **立即购买**：`POST /orders` → `checkout_batch_id IS NULL` → 单笔 `pay` 或 batch-pay
- **CartService.checkout** 为 checkout 唯一编排入口与 commit 边界；`OrderService._create_order_core(commit=False)` 参与外层事务

## 7. AI 功能路线图（后期）

| 功能 | 技术 | 说明 |
|------|------|------|
| 店铺客服对话 | support 域（已交付） | 买家↔店铺 lazy create 会话、inbox、product ref；见 ADR-007 |
| 店铺 RAG 智能客服 | 自研检索管线（pgvector 暴力 top-K）+ LLM（Mock/DeepSeek） | catalog 文本 + media 文档双源语料 → DocumentIR 落库，`ai:reindex` CLI 重建；读侧按会话范围过滤（店 / 店+商品）见 ADR-012/013；`ai-support-agent` 已落地问答闭环：NL 网关 + 意图注册表（**首批仅知识类**）+ τ 最小门禁 + 转人工兜底，买家 POST 同步 AI 回合（默认 AI、前端 PATCH 转人工、**无** `/ai/*`） |
| 推荐系统 | 协同过滤 → 自研模型 | 消费 order_items、engagement 行为数据 |
| 店铺经营助手 | DeepAgents | 读 admin API 聚合数据，长上下文 |
| 购物搭子 | LangGraph 精细编排 | 私域流量实验功能，严格控制 token 成本 |

### 7.1 AI 数据架构（后期）

- **MySQL**：唯一写源，业务操作只写 MySQL
- **PostgreSQL + pgvector**：AI 检索上下文，通过 Outbox + worker（**防腐层**）从 MySQL 同步；现况为 CLI 全量/按店重建
- **Alembic 双入口**：business（MySQL）与 ai（PostgreSQL）独立迁移
- **Tool 封装**：AI Agent 的所有数据操作通过 Tool → 业务 service，不直连数据库
- **RAG 写读分离（[ADR-012](./decision/ADR-012-RAG读写分离与change宏观安排.md)）**：写路径（离线 ingest：多源 → DocumentIR → chunk/embed → pgvector 落库）与读路径（在线检索：`vector_search` + 按会话范围过滤）仓储级分离；写/读/评测三路径复杂度正交、独立演进；change 1=底座、change 2=写侧（均已归档）、change 2.1=形状修缮（`refactor-ai-domain-architecture`）、change 3=读侧闭环（`ai-support-agent`，已落地：知识类意图 + τ 最小版，评测集/τ 标定移出）。组合根与消费边界见 [ADR-013](./decision/ADR-013-AI域组合根与消费边界.md)。

## 8. 开发流程

### 8.1 增量演进

- 按 **垂直切片（Vertical Slice）** 交付：一个 OpenSpec change = 一个可演示的能力
- 数据模型随功能增长，不预先设计全量表
- 每个 change：spec → 失败测试 → 迁移 + 实现 → CI 绿 → 合并

### 8.2 工程护栏

| 配置位置 | 用途 |
|----------|------|
| `openspec/config.yaml` | SDD 规划上下文，创建 artifact 时注入 |
| `.cursor/rules/` | 工程约定、编码纪律、会话协作规则 |
| `docs/decision/` | 架构决策记录（ADR） |
| `docs/architecture.md` | 全局架构（本文件） |

### 8.3 CI/CD 分层

| 阶段 | 内容 | 实现 |
|------|------|------|
| **Validate** | paths-filter 按路径筛选；lint（ruff + check-test-imports）独立 job；单 job 全量 pytest（无 domain matrix）；本地 `task ci` 额外含 `check-app-layer-discipline` | `.github/workflows/test.yaml` |
| **Build** | 多阶段 Dockerfile → GHCR；**仅** `vX.Y.Z` tag 触发（`workflow_dispatch` 可选） | `.github/workflows/build-push.yaml`；`Dockerfile` |
| **Deploy** | CD 部署到云服务器 + alembic upgrade | 留给 `infra-cd-compose`（后续 change） |

**CI job 结构**（`test.yaml`，name: `Run Tests`）：

```text
filter: dorny/paths-filter → 读取 .github/utils/file-filters.yaml → 输出 code=true/false
        workflow_dispatch 时强制 code=true（跳过路径筛选）
lint:   （if code=true）ruff + check-test-imports（无 services；显式 apt install ripgrep）
test:   （if code=true）单 job，无 matrix
        mysql + redis + postgres services → migrate + AI migrate → task test → upload artifact
test-failure-alert: 上游 failure/cancelled 时 exit 1
```

**触发**：`pull_request` / `push`（dev、main）；`workflow_dispatch`（无输入，全量 lint + test）。

**Build 结构**（`build-push.yaml`，name: `Build and Push Container Images`）：

```text
push vX.Y.Z tag  → semver 校验 → build + push GHCR（tag: X.Y.Z，仅此一个 tag）
workflow_dispatch → 输入 version（必填 semver）→ 同上
```

> **踩坑记录**：
>
> - `gh workflow run` / GitHub Actions API 只识别**默认分支**上的 workflow 文件。新 workflow 必须合并到默认分支后才会被 `workflow_dispatch` 事件识别。解决：合并后通过 GitHub Actions UI 手动 Run workflow，或使用 `gh workflow run "Run Tests"`（此时 workflow 已在默认分支上）。
> - **GHCR 镜像名须小写**：废止 `docker/metadata-action` 后 `build-push.yaml` 手动拼 tag，须对 `github.repository` 小写（`id: image` step → `${{ steps.image.outputs.name }}`）。owner 含大写时 buildx 报 `repository name must be lowercase`；旧 metadata-action 曾隐式处理，`v1.1.0` 首次触发回归。详见 ADR-006 决策 3。

## 9. 相关文档

### 架构决策记录（ADR）

按底座依赖顺序排列：

- [ADR-001：单体多域架构](./decision/ADR-001-单体多域架构.md)
- [ADR-002：测试与数据库策略](./decision/ADR-002-测试与数据库策略.md)
- [ADR-003：测试架构——四层分层与数据流约束](./decision/ADR-003-测试架构-四层分层与数据流约束.md)
- [ADR-004：中间件栈与异常处理架构决策](./decision/ADR-004-中间件栈与异常处理架构决策.md)
- [ADR-005：Infra 分页与列表数据流](./decision/ADR-005-infra分页与列表数据流.md)
- [ADR-006：CI 工作流与镜像发布策略](./decision/ADR-006-CI工作流与镜像发布策略.md)
- [ADR-007：多租户扩展——设计与暂缓计划](./decision/ADR-007-多租户扩展-设计与暂缓计划.md)
- [ADR-008：Git 分支生命周期与提交工作流规范](./decision/ADR-008-Git分支生命周期与提交工作流规范.md)
- [ADR-009：Redis 业务扩展与 AI 数据分层策略](./decision/ADR-009-Redis业务扩展与AI数据分层策略.md)
- [ADR-010：应用层边界纪律](./decision/ADR-010-应用层边界纪律.md)
- [ADR-011：异构数据架构的数据一致性设计](./decision/ADR-011-异构数据架构的数据一致性设计.md)
- [ADR-012：RAG 读写分离——CQS 谱系定位、仓储判据与 change 宏观安排](./decision/ADR-012-RAG读写分离与change宏观安排.md)
- [ADR-013：AI 域组合根与消费边界](./decision/ADR-013-AI域组合根与消费边界.md)

### 相关笔记（`docs/notes/`，非 ADR）

- [单例与线程锁在 FastAPI 中的适用场景](./notes/单例与线程锁在FastAPI中的适用场景.md)

### 排错与工程上下文

- [异常处理 ServerErrorMiddleware 与测试陷阱（排错）](./troubleshooting/异常处理-ServerErrorMiddleware与测试陷阱.md)
- [集成测试 AsyncClient 与 Event Loop 冲突（排错）](./troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md)
- [Gitflow：从 main 切分支导致 Graph 混乱（排错）](./troubleshooting/gitflow-从main切分支导致Graph混乱.md)
- [OpenSpec 项目上下文](../openspec/config.yaml)
