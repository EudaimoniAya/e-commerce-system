## Why

`catalog-shop` 已交付店铺实体与 `shops` 表，但尚无平台类目、商品与上下架能力。后续 `ordering` 依赖可售商品（`ProductSummary`、库存、价格）与稳定类目树。需要在下单 change 之前完成 **catalog 域类目 + 商品垂直切片**，使「管理员建类目 → 商家上架 → 公开浏览」可演示。

## What Changes

- 新增 **user 域鉴权依赖**（`app/user/deps.py`）：`require_admin`（读 `users.is_admin`，非 admin → **403**）
- 扩展 **catalog 域**：
  - 表：`categories`（平台树，`parent_id` 自引用）、`products`（`shop_id` FK）、`product_categories`（M2M + `is_primary`）
  - Alembic migration `004`（**不** seed 类目，空库起步）
- **类目 API**（REST 资源 `/categories`）：
  - `GET /categories` — 公开，扁平列表
  - `POST /categories` — `Depends(require_admin)`；body：`name`、`parent_id?`
- **商品 API**：
  - `GET /products` — 公开，仅 `is_published=true` 且店铺 `status=active`；支持 `category_id`、`limit`、`offset`
  - `GET /products/{id}` — 公开；未上架或 closed 店 → **404**
  - `GET /shops/me/products` — 商家，含未上架；`limit`/`offset`
  - `POST /products` — 商家；body **无** `shop_id`；至少 1 个类目；`category_ids` + `primary_category_id`
  - `PATCH /products/{id}` — 商家仅本店；改别人 → **403**；可改 M2M 类目
- **业务规则**：创建 `stock>0`、`price>0`；PATCH 允许 `stock=0`；店铺 `closed` 禁止 POST/PATCH 商品 → **422**；下架用 `is_published=false`（无 DELETE）
- **ProductResponse** 含嵌套 `categories: [{id, name, is_primary}]`
- 扩展 **pytest**：`tests/catalog/` 类目与商品 integration 测试
- 更新 **README.md** / **docs/architecture.md**

## Non-goals

- 不实现类目 PATCH/DELETE、商品物理 DELETE
- 不实现复杂搜索、slug SEO、促销/0 价、media 上传
- 不实现扣库存、购物车、ordering
- 不实现 `ProductSummary` 跨域 service 规范化与测试 DTO 大重构（留给后续 change）
- 不在 `UserResponse` 暴露 `is_admin`
- 不 seed 初始类目（测试/fixture 内 admin 创建）

## Capabilities

### New Capabilities

- `catalog-products`：平台类目树、商品 CRUD（无 DELETE）、M2M 关联、`require_admin` 创建类目、公开/商家读路径分离

### Modified Capabilities

- `user-auth`：新增 `require_admin` 依赖（非 admin → 403），供 catalog 管理员写操作使用

## Impact

- **业务域**：`user`（deps）、`catalog`（models/repository/service/router/schemas 扩展）
- **新增/修改**：`app/user/deps.py`、`app/catalog/*`、`alembic/versions/004_*.py`、`tests/catalog/`、`tests/conftest.py`（admin/product helpers）、`README.md`、`docs/architecture.md`
- **API**：新增 `/categories`、`/products*`、`/shops/me/products`；现有 `/shops*` 不变
- **分支**：基于 `dev` 的 `feature/catalog-products`
