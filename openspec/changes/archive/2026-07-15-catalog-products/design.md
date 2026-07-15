## Context

`catalog-shop` 已交付 `shops` 表、`get_current_shop` 依赖与 seed 管理员（`is_admin=true`）。本 change 在同一 `app/catalog/` 包内扩展类目与商品，遵循 router → service → repository → model + schemas；跨域仅用 `infra.auth.get_current_user_id` 与 `user.deps.require_admin`。

Explore 已决：平台统一类目树（adjacency list）、商品归属 shop、M2M 用 `product_categories.is_primary` 解决列表展示类目。

## Goals / Non-Goals

**Goals:**

- 实现类目 + 商品 API 闭环（admin 建类 → 商家上架 → 公开浏览）
- migration `004` 三表；TDD integration 全绿
- 与 shop 实现对齐：UUID、`str` 响应 id、422/403/404 语义、`get_current_shop`

**Non-goals:**

- DELETE 端点、DTO 全量规范化 refactor、ordering 扣库存
- 类目 seed、图片上传、促销价

## Decisions

### 1. 数据模型

#### `categories`（catalog 域，平台树）

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `parent_id` | CHAR(36) FK → categories.id | NULL = 根 |
| `name` | VARCHAR(64) | NOT NULL |
| `created_at` / `updated_at` | DATETIME | |

- `UNIQUE(parent_id, name)` 同级不重名（MySQL 对 NULL parent 按实现处理）
- **无** seed；空库

#### `products`（catalog 域）

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `shop_id` | CHAR(36) FK → shops.id | NOT NULL |
| `name` | VARCHAR(128) | NOT NULL |
| `description` | TEXT | NULL |
| `price` | DECIMAL(10,2) | NOT NULL，CNY，创建/PATCH 均 **> 0** |
| `stock` | INT | NOT NULL；创建 **> 0**；PATCH 允许 **≥ 0** |
| `is_published` | BOOLEAN | DEFAULT false |
| `image_url` | VARCHAR(512) | NULL |
| `created_at` / `updated_at` | DATETIME | |

- 索引：`ix_products_shop_id`、`ix_products_is_published`
- **不**做 `(shop_id, name)` UNIQUE（本 change）

#### `product_categories`（关联表）

| 列 | 类型 | 约束 |
|----|------|------|
| `product_id` | FK → products.id | PK 复合 |
| `category_id` | FK → categories.id | PK 复合 |
| `is_primary` | BOOLEAN | DEFAULT false |

- service 保证每个 product **至多一个** `is_primary=true`
- `primary_category_id` 必须 ∈ `category_ids`

### 2. API

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/categories` | 无 | 扁平 `[{id, parent_id, name, created_at, updated_at}]` |
| POST | `/categories` | admin | `{name, parent_id?}` → 201 |
| GET | `/products` | 无 | 已上架 + shop active；`?category_id=&limit=&offset=` |
| GET | `/products/{id}` | 无 | 否则 404 |
| GET | `/shops/me/products` | owner | 本店全部；分页 |
| POST | `/products` | owner + active shop | 201；无 shop_id |
| PATCH | `/products/{id}` | owner | 本店；非本店 403 |

**分页**：`limit` 默认 20、最大 100；`offset` 默认 0。列表响应 `{items: ProductResponse[], total, limit, offset}`。

**POST/PATCH 商品 body（类目）**：

```json
{
  "name": "...",
  "price": "99.00",
  "stock": 10,
  "description": null,
  "image_url": null,
  "is_published": false,
  "category_ids": ["uuid1", "uuid2"],
  "primary_category_id": "uuid1"
}
```

- POST：`category_ids` 至少 1 个；`primary_category_id` 必填且 ∈ `category_ids`
- PATCH：字段均可选；若提供类目字段，规则同上

**ProductResponse**：

```json
{
  "id": "...",
  "shop_id": "...",
  "name": "...",
  "description": null,
  "price": "99.00",
  "stock": 10,
  "is_published": false,
  "image_url": null,
  "categories": [
    {"id": "...", "name": "手机", "is_primary": true}
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

**closed 店铺**：`POST/PATCH /products*` → **422**（shop closed）。

**公开读过滤**：`GET /products` JOIN shops WHERE `products.is_published` AND `shops.status='active'`；按 `category_id` 时 JOIN `product_categories`。

### 3. 依赖链

```text
POST /categories
  → Depends(require_admin)           # user/deps.py
  → catalog.service.create_category

POST /products
  → Depends(get_current_shop)        # catalog/deps.py；closed → 422 在 service
  → catalog.service.create_product   # shop_id 从 shop 推断

PATCH /products/{id}
  → Depends(get_current_user_id)
  → load product → owner shop 校验 → 403 / closed 422
```

`require_admin` 实现：查 `UserRepository.get_by_id`；`is_admin` false → 403；用户不存在 → 401。

### 4. 路由注册顺序

在 `catalog/router.py` 中 **`GET /shops/me/products` 须先于 `GET /shops/{shop_id}`**（与现有 `/shops/me` 同理），避免路径冲突。

### 5. 测试策略

- 扩展 `conftest`：`admin_auth_headers`（seed 邮箱登录）、`create_category` helper、`product_payload`
- 新测试文件：`test_admin_categories.py`、`test_categories_public.py`、`test_create_product.py`、`test_my_products.py`、`test_public_products.py`、`test_update_product.py`
- `@pytest.mark.integration` + `AsyncClient`

### 6. Apply 顺序（与 tasks.md 一致）

1. **§1 红**：编写全部失败测试；路由未挂载时 category/product HTTP 用例多为 **404**
2. **§2 迁移**：`Category` / `Product` / `ProductCategory` ORM + migration `004`
3. **§3 require_admin**：`user/deps.py`（须在挂 `POST /categories` 的 router 之前）
4. **§4 绿**：schemas → repository → service → router

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| MySQL UNIQUE(parent_id, name) 与 NULL parent | migration 验证；同级重名 422 |
| 列表 JOIN 性能 | MVP 数据量小；索引 + limit |
| PATCH 部分更新类目 | 仅当 body 含 category_ids 时全量替换关联 |

## Migration Plan

1. `004` upgrade：categories、products、product_categories
2. `task migrate` + `task ci`
3. downgrade：按 FK 顺序 drop 关联表 → products → categories

## Open Questions

- （已决）A–F：至少 1 类目、M2M body、price 始终 >0、Response 含 categories、空库、category_id 筛选
