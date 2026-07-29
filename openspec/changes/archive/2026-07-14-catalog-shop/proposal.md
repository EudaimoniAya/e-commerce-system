## Why

`user-auth` 已交付注册/登录/JWT，但尚无店铺实体与商家开店能力。后续 `catalog-products`（类目、商品）与 `ordering` 均要求商品归属店铺、商家通过 JWT 管理自己的店。需要在商品 change 之前完成 **catalog 域店铺垂直切片**，使「注册 → 开店 → 查看/修改店铺 → 公开店铺页」可演示；同时为后续管理员能力预埋 `users.is_admin` 与 seed 管理员账号。

## What Changes

- 扩展 **user 域**：`users` 表新增 `is_admin`（BOOLEAN，默认 false）；migration seed 一名平台管理员（`114514yyut@qq.com` / 明文 `1919810810`，migration 写入 `password_hash`）
- 新增 **catalog 业务域**（`app/catalog/`）：`shops` 表与 router → service → repository → model + schemas 分层
- **店铺模型**：`owner_user_id` FK → `users.id`，**UNIQUE**（当前 1 用户 1 店，未来多店铺可移除此约束）；`name` 全站唯一；`status` 为 `active` | `closed`
- **API**：
  - `POST /shops` — 需 JWT；任意注册用户可开店；已有店返回 422
  - `GET /shops/me` — 需 JWT；返回当前用户店铺；无店返回 **404**
  - `PATCH /shops/me` — 需 JWT；更新店名、简介、`logo_url`、关店（`status=closed`）
  - `GET /shops/{shop_id}` — 公开；`closed` 店铺仍返回 **200** 且 body 含 `status: closed`（供前端展示「店铺已关闭」）
- **Alembic**：`003` migration（`is_admin` + `shops` + seed admin）；`alembic/env.py` 导入 `app.catalog.models`
- 扩展 **pytest**：`tests/catalog/` integration 测试（开店、重复开店 422、me 404/200、patch、公开 get、closed 200）
- 更新 **README.md** / **docs/architecture.md** 阶段描述

## Non-goals

- 不实现 `is_seller`；商家身份由「是否拥有 shop」表达，专用端点 `GET /shops/me`
- 不实现 `require_admin` 依赖、`POST /categories`、商品、类目（留给 `catalog-products`）
- 不实现 `user-admin` 封禁（用户/店铺 banned）、平台治理后台
- 不实现店铺 `banned` 状态、异步物理删除、软删（`closed` 仅标记；异步任务需未来 infra）
- 不实现 `logo_url` / 图片上传（仅 VARCHAR 外链字段）；media 域以后引入
- 不实现 slug SEO、分页基础设施、多店铺（仅 schema 预留：文档记录未来可 drop UNIQUE）
- 不在 `UserResponse` / `GET /users/me` 暴露 `is_admin`（本 change 无 admin 端点消费）

## Capabilities

### New Capabilities

- `catalog-shop`：店铺创建/查询/更新；`shops` 表；`app/catalog/` 域内分层；公开 `GET /shops/{id}` 与商家 `GET/PATCH /shops/me`

### Modified Capabilities

- `user-auth`：`users` 表 SHALL 包含 `is_admin`；migration SHALL seed 一名 `is_admin=true` 的管理员用户

## Impact

- **业务域**：`user`（`is_admin` 列 + seed）、`catalog`（首个 catalog 限界上下文）
- **新增/修改文件**：`app/catalog/`（`router.py`、`service.py`、`repository.py`、`models.py`、`schemas.py`、`deps.py`）、`app/user/models.py`、`app/main.py`、`alembic/versions/003_*.py`、`alembic/env.py`、`tests/catalog/`、`tests/conftest.py`（shop helpers）、`README.md`、`docs/architecture.md`
- **API**：新增 `/shops`、`/shops/me`、`/shops/{shop_id}`；现有 auth/health 不变
- **分支**：基于 `dev` 的 `feature/catalog-shop`
