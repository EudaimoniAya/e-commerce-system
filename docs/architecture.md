# 项目架构设计

> 本文档描述 AI 赋能电商个人项目的整体架构。详细的设计决策见 [docs/decision/](./decision/)（ADR）；个人学习笔记见 [docs/notes/](./notes/)。

## 1. 项目概述

本项目是一个 **AI 赋能的电商平台** 个人练习项目。核心思路是：**以传统电商业务为底座，在其上叠加 AI 能力**，而非从零做一个纯 AI 应用。

- **当前阶段**：user 域**手机号 + SMS OTP 认证**、**catalog 域店铺 + 类目/商品**、**ordering 域买家订单与购物车**、**engagement 域用户收藏** 已交付（SMS send/register/login、密码登录、PATCH `/users/me`、JWT；开店/me/patch/公开 GET、平台类目树、商品 CRUD/上下架、公开浏览；买家立即购买与购物车 checkout/batch-pay、支付桩/发货/确认收货/取消与懒释放；`POST/GET/DELETE /favorites*`、`POST /favorites/batch-delete`）；浏览记录等待后续 `engagement-browse-events` change
- **演进方式**：垂直切片增量交付，SDD + TDD，CI 从第一天启用，大版本完成后 CD 部署
- **预估规模**：全项目约 1 万行，电商底座约 3000 行

## 2. 技术栈

| 层次 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 业务 API 与 AI API 统一入口 |
| 业务数据库 | MySQL | 唯一真实数据源（Single Source of Truth） |
| ORM / 迁移 | SQLAlchemy + Alembic | 初期仅 business 迁移入口 |
| AI 框架（后期） | LangChain / LangGraph / DeepAgents | 按功能分模块引入 |
| 向量数据库（后期） | PostgreSQL + pgvector | AI 检索上下文，与业务库分离 |
| 工程规范 | OpenSpec (SDD) + pytest (TDD) + CI | 详见工程约定 |

## 3. 架构总览：二维结构

系统采用 **「业务域（纵切）× 平台能力（横切）」** 的二维架构：

```text
                    ┌─────────────────────────────────────┐
                    │         路由 / 编排层               │
                    │   HTTP 路由 + 意图识别 / AI 分流    │
                    └──────────┬──────────────┬───────────┘
                               │              │
          ┌────────────────────┼──────────────┼────────────────────┐
          │  纵轴：业务域       │              │  邻接：AI 能力域    │
          │                    ▼              ▼                    │
          │  ┌──────────┐ ┌──────────┐ ┌──────────┐  ┌──────────┐ │
          │  │   user   │ │ catalog  │ │ ordering │  │    ai    │ │
          │  │ 用户认证  │ │ 商品目录  │ │ 订单购物车│  │ RAG/推荐 │ │
          │  └──────────┘ └──────────┘ └──────────┘  │ 助手/搭子 │ │
          │  ┌──────────┐                             └────┬─────┘ │
          │  │engagement│                                   │       │
          │  │收藏/浏览  │◄──────────────────────────────────┘       │
          │  └──────────┘         Tool 调用业务 service              │
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
| `ordering` | 买家订单、购物车、checkout 分组、库存预留/释放、支付桩、发货与确认收货 | Order, OrderItem, CartItem, CheckoutBatch | **MVP（买家路径 + 购物车已实现）** |
| `engagement` | 用户收藏（浏览记录待后续 change） | UserFavorite（已实现）；BrowseEvent（待实现） | **Phase 2（收藏已实现）** |
| `ai` | RAG、推荐、经营助手、购物搭子 | — | AI 阶段 |

### 3.2 邻接：AI 能力域

AI **不是** 横切进每个业务域的内部，而是与业务域 **并列** 的独立能力域：

- Agent 通过 **Tool** 调用各业务域的 **service**，不直连 repository 或 ORM
- RAG 检索读 PostgreSQL 向量副本，强一致数据（库存、价格、订单状态）走 Tool 实时查 MySQL
- 路由层负责 **传统 API 与 AI 的分流编排**（意图识别等）

### 3.3 横轴：平台能力

| 模块 | 职责 |
|------|------|
| `infra/` | 配置、数据库 Session、**Redis 客户端**、JWT、健康/readiness 探针、**结构化日志**、**统一 error JSON**、**分页（已实现）**|
| `events/`（后期） | Outbox、领域事件，驱动 MySQL → pgvector ACL 同步 |
| `shared/`（可选） | 无业务含义的公共类型，保持极简 |

## 4. 域间协作规则

### 4.1 依赖方向

```text
✓ 跨域：ordering.service → catalog.service → 返回 schema（DTO）
✓ 域内：router → service → repository → ORM model
✓ AI：ai.tools → 各域 service
✓ 各域 → infra

✗ 跨域 import 对方的 ORM model 或 repository
✗ 业务域 import ai
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

## 5. 目录结构

### 5.1 当前骨架（user + catalog + ordering + engagement + infra）

```text
e-commerce-system/
├── app/
│   ├── main.py                   # create_app() 工厂：logging → middleware → handlers → 路由
│   ├── infra/
│   │   ├── config.py             # DATABASE_URL、REDIS_URL、APP_ENV、jwt_*、sms_*、ORDER_RESERVATION_TTL_SECONDS
│   │   ├── database.py           # async engine、AsyncSession、Base、get_db、reset_engine
│   │   ├── redis.py              # redis.asyncio 连接池、get_redis、reset_redis
│   │   ├── auth.py               # PyJWT、OAuth2PasswordBearer、get_current_user_id
│   │   ├── logging/              # loguru setup、InterceptHandler、RequestIDMiddleware
│   │   ├── errors/               # 全局 exception handlers、统一 error JSON
│   │   ├── health/               # 存活探针 GET /health
│   │   ├── readiness/            # 就绪探针 GET /health/ready（MySQL + Redis 检查）
│   │   ├── pagination/           # 分页基础设施（PaginationParams、get_pagination_params、Paginated[TResponse]）
│   │   └── models/               # infra 验证用 ORM（_infra_migration_smoke）
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
│   └── engagement/               # 用户行为域（收藏已实现）
│       ├── router.py             # POST/GET/DELETE /favorites*、POST /favorites/batch-delete
│       ├── service.py            # FavoriteService：CRUD、列表分类、batch_delete
│       ├── repository.py
│       ├── models.py             # user_favorites
│       ├── schemas.py
│       └── deps.py
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
│       └── 009_engagement_favorites.py  # user_favorites
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
│   └── engagement/               # 用户收藏 integration
├── scripts/                      # devbox MySQL/Redis 运维、Allure 打开报告、test-import 检查（无 curl 烟雾脚本）
│   ├── devbox_mysql_up.sh / devbox_mysql_down.sh / devbox_mysql_reset.sh
│   ├── devbox_redis_up.sh / devbox_redis_down.sh
│   ├── allure_open_report.sh     # Task latest:report
│   └── check_no_test_cross_imports.sh  # Task check-test-imports；依赖 rg（ripgrep），见 test-architecture / infra-ci spec
├── .github/workflows/ci.yml      # DATABASE_URL + REDIS_URL + JWT_SECRET_KEY；migrate + task ci
└── ...
```

**应用入口（`create_app`）**：按序组装 `setup_logging(settings)` → `RequestIDMiddleware`（纯 ASGI，`X-Request-ID` 透传/生成）→ `register_exception_handlers(app)` → 各域 router。错误响应统一为 `{"error": {"code", "message", "request_id"}}`（详见 `infra-api-errors` spec）。日志经 loguru 输出至 stderr 与 `logs/app.log`（development/production；test 仅 stderr 且 level=WARNING）。详见 [中间件栈与异常处理架构决策（ADR-004）](./decision/ADR-004-中间件栈与异常处理架构决策.md)。

**`users` 表（user 域）**：`id`（UUID PK，JWT `sub` 锚点）、`phone`（VARCHAR 20，UNIQUE，业务主标识）、`email`（可空，仅资料）、`password_hash`（可空，SMS 注册用户须设密码）、`nickname`、`is_active`、`is_admin`（不对外暴露）、`created_at`、`updated_at`。SMS OTP 存 Redis（`sms:otp:{phone}`、`sms:verify_fail:{phone}`、`sms:daily:{phone}:{date}`），见 `user/sms_service.py`。

**`shops` 表（catalog 域）**：`id`（UUID PK）、`owner_user_id`（FK → `users.id`，UNIQUE，当前一用户一店）、`name`（UNIQUE）、`description`、`logo_url`、`status`（`active` | `closed`）、`created_at`、`updated_at`。跨域仅通过 `infra.auth.get_current_user_id` 解析 JWT，不在 `User` ORM 上声明跨域 relationship。

**`categories` 表（catalog 域）**：`id`（UUID PK）、`parent_id`（FK → `categories.id`，NULL 为根）、`name`（VARCHAR 64）、`created_at`、`updated_at`；`UNIQUE(parent_id, name)` 同级不重名；**无 seed**，空库起步。

**`products` 表（catalog 域）**：`id`（UUID PK）、`shop_id`（FK → `shops.id`）、`name`、`description`、`price`（DECIMAL 10,2，CNY）、`stock`、`is_published`（默认 false）、`image_url`、`created_at`、`updated_at`；索引 `ix_products_shop_id`、`ix_products_is_published`。

**`product_categories` 表（catalog 域）**：`(product_id, category_id)` 复合 PK、`is_primary`（BOOLEAN）；service 保证每个商品至多一个主类目；`primary_category_id` 必须 ∈ `category_ids`。

**`orders` 表（ordering 域）**：`id`（UUID PK）、`buyer_user_id`（FK 语义 → `users.id`）、`shop_id`（FK 语义 → `shops.id`）、`status`（`awaiting_payment` | `confirmed` | `shipped` | `completed` | `cancelled`）、`cancel_reason`（可空）、`total_amount`（DECIMAL 12,2）、`expires_at`（待支付预留截止）、`initiated_by`（`buyer` | `seller`）、`checkout_batch_id`（可空 FK → `checkout_batches.id`；立即购买为 NULL）、`created_at`、`updated_at`；索引含 `ix_orders_buyer_user_id`、`ix_orders_shop_id`、`ix_orders_status`、`ix_orders_expires_at`、`ix_orders_checkout_batch_id`。跨域仅存 FK 字段，**不**声明跨域 relationship。

**`order_items` 表（ordering 域）**：`id`（UUID PK）、`order_id`（FK → `orders.id`）、`product_id`（快照关联）、`product_name`、`unit_price`（DECIMAL 10,2）、`qty`（> 0）。创建时写入价格与商品名快照；1 订单 = 1 店 + 多行。

**`cart_items` 表（ordering 域）**：`id`（UUID PK）、`user_id`（FK → `users.id`）、`product_id`（仅存 ID，展示走 catalog.service）、`qty`（> 0）、`created_at`、`updated_at`；`UNIQUE(user_id, product_id)`；索引 `ix_cart_items_user_id`。暂存不占库存、不建单；**不**跨域 ORM relationship。

**`checkout_batches` 表（ordering 域）**：`id`（UUID PK）、`buyer_user_id`（FK → `users.id`）、`created_at`。轻量分组标签（无行项目/总价/status）；cart checkout 时创建，供 `GET /orders/checkout-batches/{id}` 层级展示；支付走通用 `POST /orders/batch-pay`。

**库存预留（catalog ↔ ordering）**：创建订单时 ordering service 在同一事务内调用 catalog `reserve_stock`（条件 `UPDATE ... SET stock=stock-qty WHERE stock>=qty`）；取消或懒过期释放时调用 `release_stock`。cart checkout 在单事务内按店 split 多次建单（`_create_order_core(commit=False)`）后统一 commit。ordering **不得** import catalog ORM/repository。

**购物车读路径**：`GET /cart` 批量调用 `catalog.service.get_purchasable_products` enrichment，按店分组；不可购项进 `invalid_items`（不自动删除）。列表展示 catalog 实时价；成交价以 checkout 建单时 `order_items` 快照为准。

**`user_favorites` 表（engagement 域）**：`id`（UUID PK）、`user_id`（FK → `users.id`）、`product_id`（仅存 ID，展示走 catalog.service）、`created_at`；`UNIQUE(user_id, product_id)`；索引 `ix_user_favorites_user_id`。**不**存 price/name/image 快照；**不**跨域 ORM relationship。语义为**用户偏好**，与 ordering 域 `cart_items`（购买意图）独立。

**收藏读路径**：`GET /favorites` 分页读 `user_favorites` → 批量 `catalog.service.get_products_for_engagement` → 分类为 `items`（可公开展示；前端再调 `GET /products/{id}`）与 `unavailable_items`（含 `reason`：`product_unpublished` | `shop_closed` | `not_found`，及 `product_name`/`image_url` enrichment）。POST 收藏校验 catalog 行存在即可（不要求可购）。`POST /favorites/batch-delete` 接受 `{ "product_ids": [...] }`（对标 `POST /orders/batch-pay`）；engagement **不得** import catalog ORM/repository。catalog 跨域 DTO：`EngagementProduct` + `get_products_for_engagement`（与 `get_purchasable_products` 共用 repository 批量 SQL）。

### 5.2 规划中的完整结构

随垂直切片增量补充 `engagement/`（浏览等）、后期的 `ai/`、`events/` 等。`user/`、`catalog/`、`ordering/`、`engagement/`（收藏）与 `infra/auth.py` 已按 router → service → repository → model + schemas 分层实现。

```text
app/
├── main.py                       # create_app()：setup_logging → middleware → handlers → routers
├── infra/
│   ├── health/                   # 已实现
│   ├── readiness/                # 已实现（MySQL + Redis 聚合检查）
│   ├── redis.py                  # 已实现（redis.asyncio、get_redis）
│   ├── logging/                  # 已实现（loguru、request_id、logs/app.log）
│   ├── errors/                   # 已实现（统一 error JSON、全局 handlers）
│   ├── config.py                 # 已实现（含 jwt_*、app_env）
│   ├── database.py               # 已实现
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
├── engagement/                   # 收藏已实现；browse_events 待后续 change
│   ├── router.py
│   ├── service.py
│   ├── repository.py
│   ├── models.py
│   ├── schemas.py
│   └── deps.py
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
- 浏览记录（Phase 2 待实现，归入 engagement 域）

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
| 店铺 RAG 智能客服 | LangChain Retriever | 商品描述、FAQ 语义检索 |
| 推荐系统 | 协同过滤 → 自研模型 | 消费 order_items、engagement 行为数据 |
| 店铺经营助手 | DeepAgents | 读 admin API 聚合数据，长上下文 |
| 购物搭子 | LangGraph 精细编排 | 私域流量实验功能，严格控制 token 成本 |

### 7.1 AI 数据架构（后期）

- **MySQL**：唯一写源，业务操作只写 MySQL
- **PostgreSQL + pgvector**：AI 检索上下文，通过 Outbox + 异步 ACL 从 MySQL 同步
- **Alembic 双入口**：business（MySQL）与 ai（PostgreSQL）独立迁移
- **Tool 封装**：AI Agent 的所有数据操作通过 Tool → 业务 service，不直连数据库

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
| **Validate** | paths-filter 按路径筛选；lint（ruff + check-test-imports）独立 job；单 job 全量 pytest（无 domain matrix） | `.github/workflows/test.yaml`（`feature/infra-ci-workflows`） |
| **Build** | 多阶段 Dockerfile → GHCR；**仅** `vX.Y.Z` tag 触发（`workflow_dispatch` 可选） | `.github/workflows/build-push.yaml`；`Dockerfile` |
| **Deploy** | CD 部署到云服务器 + alembic upgrade | 留给 `infra-cd-compose`（后续 change） |

**CI job 结构**（`test.yaml`，name: `Run Tests`）：

```text
filter: dorny/paths-filter → 读取 .github/utils/file-filters.yaml → 输出 code=true/false
        workflow_dispatch 时强制 code=true（跳过路径筛选）
lint:   （if code=true）ruff + check-test-imports（无 services；显式 apt install ripgrep）
test:   （if code=true）单 job，无 matrix
        mysql + redis services → migrate → task test → upload artifact
test-failure-alert: 上游 failure/cancelled 时 exit 1
```

**触发**：`pull_request` / `push`（dev、main）；`workflow_dispatch`（无输入，全量 lint + test）。

**Build 结构**（`build-push.yaml`，name: `Build and Push Container Images`）：

```text
push vX.Y.Z tag  → semver 校验 → build + push GHCR（tag: X.Y.Z，仅此一个 tag）
workflow_dispatch → 输入 version（必填 semver）→ 同上
```

> **踩坑记录**：`gh workflow run` / GitHub Actions API 只识别**默认分支**上的 workflow 文件。新 workflow 必须合并到默认分支后才会被 `workflow_dispatch` 事件识别。解决：合并后通过 GitHub Actions UI 手动 Run workflow，或使用 `gh workflow run "Run Tests"`（此时 workflow 已在默认分支上）。

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

### 相关笔记（`docs/notes/`，非 ADR）

- [单例与线程锁在 FastAPI 中的适用场景](./notes/单例与线程锁在FastAPI中的适用场景.md)

### 排错与工程上下文

- [异常处理 ServerErrorMiddleware 与测试陷阱（排错）](./troubleshooting/异常处理-ServerErrorMiddleware与测试陷阱.md)
- [集成测试 AsyncClient 与 Event Loop 冲突（排错）](./troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md)
- [Gitflow：从 main 切分支导致 Graph 混乱（排错）](./troubleshooting/gitflow-从main切分支导致Graph混乱.md)
- [OpenSpec 项目上下文](../openspec/config.yaml)
