## Context

`user-auth` 已交付 JWT 与 `users` 表，尚无 catalog 业务域。架构规划商品归属店铺（N:1），店主与 user 当前 1:1（`shops.owner_user_id` UNIQUE）。后续 `catalog-products` 需要平台管理员创建类目，本 change 仅预埋 `users.is_admin` 与 seed 管理员，**不**实现 `require_admin` 或类目 API。

约束来自 explore 决策与 `.cursor/rules/cross-domain-imports.mdc`：

- `shops` 表与 ORM 归属 **catalog 域**；FK 在 shop 侧指向 `users.id`，**不在** `User` ORM 上声明跨域 `relationship`
- 不用 `is_seller`；商家身份由 `GET /shops/me` 表达
- 店铺 `closed` 仅标记，异步物理删除留给未来 infra + `user-admin`

## Goals / Non-Goals

**Goals:**

- 实现 `POST /shops`、`GET /shops/me`、`PATCH /shops/me`、`GET /shops/{shop_id}` 可演示闭环
- 建立 catalog 域分层样板：`router → service → repository → model + schemas + deps`
- `users.is_admin` 列 + migration seed 管理员（`114514yyut@qq.com`）
- Alembic `003` migration；TDD integration 测试全绿

**Non-Goals:**

- `require_admin`、`POST /categories`、商品、media 上传
- `is_seller`、`UserResponse.is_admin` 暴露、封禁（`banned`）、async 删店
- slug、分页 infra、多店铺实现（仅文档记录扩展路径）

## Decisions

### 1. 模块布局

```text
app/
├── main.py                          # 挂载 catalog router
├── user/
│   └── models.py                    # 增加 is_admin 列
└── catalog/
    ├── router.py                    # /shops, /shops/me, /shops/{shop_id}
    ├── service.py                   # create_shop, get_my_shop, update_my_shop, get_public_shop
    ├── repository.py
    ├── models.py                    # Shop ORM
    ├── schemas.py                   # ShopCreate, ShopUpdate, ShopResponse
    └── deps.py                      # get_current_shop（owner 查库，供 PATCH 等）

alembic/versions/003_*.py            # is_admin + shops + seed admin
tests/catalog/
```

**跨域**：catalog 使用 `infra.auth.get_current_user_id` 解析 JWT；**不** import `user.repository` 或 `user.models`（除 migration seed 脚本可在 revision 内用 SQL）。

### 2. 数据模型

#### `users` 变更（user 域）

| 列 | 类型 | 说明 |
|----|------|------|
| `is_admin` | `BOOLEAN NOT NULL DEFAULT false` | 平台管理员 |

#### `shops`（catalog 域）

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | `CHAR(36)` | PK | UUID v4 |
| `owner_user_id` | `CHAR(36)` | FK → `users.id`, **UNIQUE** | 店主；UNIQUE 强制 1:1 |
| `name` | `VARCHAR(128)` | **UNIQUE** | 全站唯一店名 |
| `description` | `TEXT` | NULL | 简介 |
| `logo_url` | `VARCHAR(512)` | NULL | 外链 URL，不上传 |
| `status` | `VARCHAR(16)` | NOT NULL, default `active` | `active` \| `closed` |
| `created_at` | `DATETIME` | | |
| `updated_at` | `DATETIME` | | |

**多店铺扩展（未实现）**：未来 change 移除 `uq_shops_owner_user_id`，引入 `shop_members`；`products.shop_id` 语义不变。

### 3. API 与状态码

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/shops` | Bearer | body: `name`, optional `description`, `logo_url`；201 |
| GET | `/shops/me` | Bearer | 200 + shop；无店 **404** |
| PATCH | `/shops/me` | Bearer | 更新 `name`/`description`/`logo_url`/`status`；200 |
| GET | `/shops/{shop_id}` | 无 | 200；`closed` 仍 200 且含 `status` |

- 重复开店（已有 shop）→ **422**
- 店名冲突 → **422**
- 未认证访问 `/shops/me` 或 `POST /shops` 或 `PATCH /shops/me` → **401**
- PATCH 非 owner（无 shop）→ **404**（与 me 一致）

公开 `GET /shops/{id}`：`closed` 店铺返回完整 `ShopResponse`（含 `status: closed`），前端自行展示「店铺已关闭」；**不**返回 404。

### 4. Seed 管理员

Migration `upgrade()` 在 `shops` 表创建后插入（或 upsert）管理员用户：

- `email`: `114514yyut@qq.com`
- `password` 明文（仅 migration 使用）: `1919810810`（10 位，符合登录 API 8–32 位规则）
- `password_hash`: 使用与 user 域相同的 **pwdlib** 算法在 migration 中生成（Python `op.get_bind()` + 一次性 hash，或 Alembic 外预先计算常量 hash 写入 revision）
- `nickname`: `平台管理员`（或 `Admin`）
- `is_admin`: `true`
- `is_active`: `true`

开发/CI 可通过 `POST /auth/login` 使用上述凭据登录管理员账号。

### 5. 依赖链

```text
POST /shops
  → Depends(get_current_user_id)     # infra/auth
  → catalog.service.create_shop(user_id, ...)

GET /shops/me / PATCH /shops/me
  → Depends(get_current_user_id)
  → catalog.service / deps.get_current_shop

GET /shops/{shop_id}
  → 无鉴权
  → catalog.service.get_shop_by_id
```

`require_admin` **本 change 不添加**；`catalog-products` 在 `user/deps.py` 新增。

### 6. 测试策略

- `@pytest.mark.integration`；`httpx.AsyncClient`；`reset_engine` fixture（同 user-auth）
- `tests/conftest.py` 扩展：`create_shop` helper、`shop_owner` fixture
- 覆盖：开店 201、重复 422、me 404/200、patch name/closed、公开 get active/closed、店名冲突 422、未认证 401
- seed admin：integration 测试断言 DB 存在 `is_admin=true` 且 email 匹配（不要求本 change 测 login admin）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| seed 凭据泄露（明文写入 design） | 仅本地/CI 开发用；生产部署前轮换密码 |
| `closed` 店铺仍公开可见 | 有意为之，支持前端关店页；平台封禁用未来 `banned` |
| 一 change 改 user + catalog 两域 | proposal 已声明；各域自有表，FK 在 shop 侧 |
| migration 内 pwdlib hash | revision 内 import pwdlib 或使用预计算 hash 常量，与线上一致 |

## Migration Plan

1. `alembic upgrade head`：`003` 添加 `is_admin`、创建 `shops`、seed admin
2. `task ci` 全绿
3. rollback：`003` downgrade 删 `shops`、删 `is_admin` 列（seed 用户可选删或留）

## Open Questions

- （已决）seed 密码：`1919810810`。
