# 项目架构设计

> 本文档描述 AI 赋能电商个人项目的整体架构。详细的设计决策见 [docs/decision/](./decision/)。

## 1. 项目概述

本项目是一个 **AI 赋能的电商平台** 个人练习项目。核心思路是：**以传统电商业务为底座，在其上叠加 AI 能力**，而非从零做一个纯 AI 应用。

- **当前阶段**：user 域认证、**catalog 域店铺 + 类目/商品垂直切片** 已交付（注册/登录/JWT、`shops` 表、开店/me/patch/公开 GET；平台类目树、商品 CRUD/上下架、公开浏览）；继续扩展 ordering 等 MVP 域
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
| `ordering` | 订单、购物车、下单扣库存 | Order, OrderItem, CartItem | MVP + 购物车 |
| `engagement` | 收藏、浏览记录 | UserFavorite, BrowseEvent | Phase 2 |
| `ai` | RAG、推荐、经营助手、购物搭子 | — | AI 阶段 |

### 3.2 邻接：AI 能力域

AI **不是** 横切进每个业务域的内部，而是与业务域 **并列** 的独立能力域：

- Agent 通过 **Tool** 调用各业务域的 **service**，不直连 repository 或 ORM
- RAG 检索读 PostgreSQL 向量副本，强一致数据（库存、价格、订单状态）走 Tool 实时查 MySQL
- 路由层负责 **传统 API 与 AI 的分流编排**（意图识别等）

### 3.3 横轴：平台能力

| 模块 | 职责 |
|------|------|
| `infra/` | 配置、数据库 Session、健康探针、readiness、公共异常、分页 |
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

### 5.1 当前骨架（user + catalog + infra）

```text
e-commerce-system/
├── app/
│   ├── main.py                   # FastAPI 入口，挂载 health / readiness / user / catalog 路由
│   ├── infra/
│   │   ├── config.py             # DATABASE_URL、APP_ENV、jwt_* 配置
│   │   ├── database.py           # async engine、AsyncSession、Base、get_db、reset_engine
│   │   ├── auth.py               # PyJWT、OAuth2PasswordBearer、get_current_user_id
│   │   ├── health/               # 存活探针 GET /health
│   │   ├── readiness/            # 就绪探针 GET /health/ready（MySQL 检查）
│   │   └── models/               # infra 验证用 ORM（_infra_migration_smoke）
│   ├── user/                     # 用户域（router → service → repository → model）
│   │   ├── router.py             # POST /auth/register|login，GET /users/me
│   │   ├── service.py            # 注册/登录、pwdlib 哈希
│   │   ├── repository.py
│   │   ├── models.py             # users 表（含 is_admin）
│   │   ├── schemas.py
│   │   └── deps.py               # get_current_user、require_admin
│   └── catalog/                  # 商品目录域（shop + 类目/商品已实现）
│       ├── router.py             # categories/products/shops 路由
│       ├── service.py            # 类目、商品、店铺业务逻辑
│       ├── repository.py
│       ├── models.py             # shops、categories、products、product_categories
│       ├── schemas.py
│       └── deps.py               # get_current_shop
├── alembic/
│   └── versions/
│       ├── 001_create_infra_migration_smoke.py
│       ├── 002_create_users.py
│       ├── 003_catalog_shop.py   # users.is_admin + shops 表 + seed 管理员
│       └── 004_catalog_products.py  # categories、products、product_categories（无 seed）
├── tests/
│   ├── conftest.py               # httpx AsyncClient、reset_engine、auth/shop/category helper
│   ├── health/
│   ├── infra/
│   ├── user/                     # 注册/登录/me integration（12 项）
│   └── catalog/                  # 店铺 + 类目/商品 + seed integration（41 项）
├── scripts/
│   └── catalog_shop_curl_smoke.sh
├── .github/workflows/ci.yml      # DATABASE_URL + JWT_SECRET_KEY；migrate + task ci
└── ...
```

**`shops` 表（catalog 域）**：`id`（UUID PK）、`owner_user_id`（FK → `users.id`，UNIQUE，当前一用户一店）、`name`（UNIQUE）、`description`、`logo_url`、`status`（`active` | `closed`）、`created_at`、`updated_at`。跨域仅通过 `infra.auth.get_current_user_id` 解析 JWT，不在 `User` ORM 上声明跨域 relationship。

**`categories` 表（catalog 域）**：`id`（UUID PK）、`parent_id`（FK → `categories.id`，NULL 为根）、`name`（VARCHAR 64）、`created_at`、`updated_at`；`UNIQUE(parent_id, name)` 同级不重名；**无 seed**，空库起步。

**`products` 表（catalog 域）**：`id`（UUID PK）、`shop_id`（FK → `shops.id`）、`name`、`description`、`price`（DECIMAL 10,2，CNY）、`stock`、`is_published`（默认 false）、`image_url`、`created_at`、`updated_at`；索引 `ix_products_shop_id`、`ix_products_is_published`。

**`product_categories` 表（catalog 域）**：`(product_id, category_id)` 复合 PK、`is_primary`（BOOLEAN）；service 保证每个商品至多一个主类目；`primary_category_id` 必须 ∈ `category_ids`。

### 5.2 规划中的完整结构

随垂直切片增量补充 `ordering/`、`engagement/` 等业务域，以及后期的 `ai/`、`events/` 等。`user/`、`catalog/`（shop + 类目/商品）与 `infra/auth.py` 已按 router → service → repository → model + schemas 分层实现。

```text
app/
├── main.py
├── infra/
│   ├── health/                   # 已实现
│   ├── readiness/                # 已实现
│   ├── config.py                 # 已实现（含 jwt_*）
│   ├── database.py               # 已实现
│   └── auth.py                   # 已实现
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
├── ordering/                     # MVP（待实现）
├── engagement/                   # Phase 2
├── events/                       # 后期
└── ai/                           # 后期
```

## 6. 电商 MVP 范围

### 6.1 包含

- 用户注册 / 登录（JWT）
- 商品 CRUD、类目、上下架
- 创建订单、查询订单、取消订单
- 库存扣减与订单快照（价格、商品名）
- 购物车（Phase 2，归入 ordering 域）
- 收藏、浏览记录（Phase 2，归入 engagement 域）

### 6.2 明确不做（MVP）

| 模块 | 原因 |
|------|------|
| 支付 | 流程长、合规多，对 AI 赋能价值低 |
| 物流 | 同上 |
| 优惠券 / 促销 | 复杂度高，非 AI 核心素材 |
| 多店铺 / 多租户 | 单店 MVP 足够 |
| SKU 多规格 | 一个 product = 一个 SKU，后期再扩展 |

### 6.3 订单状态（极简）

```text
pending → confirmed → completed
         ↘ cancelled
```

创建订单后扣库存，直接进入 `confirmed`（无支付环节）。

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

| 阶段 | 内容 |
|------|------|
| 每次 push | lint + pytest |
| 合并 main / tag | Docker 镜像构建 |
| 大版本 tag | CD 部署到云服务器 + alembic upgrade |

## 9. 相关文档

- [单体多域架构决策](./decision/单体多域架构.md)
- [测试与数据库策略（ADR）](./decision/测试与数据库策略.md)
- [集成测试 AsyncClient 与 Event Loop 冲突（排错）](./troubleshooting/集成测试-AsyncClient与EventLoop线程冲突.md)
- [OpenSpec 项目上下文](../openspec/config.yaml)
