## Why

`media-storage` 已归档：media 平台域可 upload / `GET /media/{id}/file` / delete，业务表仍使用 `products.image_url`、`shops.logo_url` 外链，`users` 无头像列。当前无生产线上存量，可在本 change 硬切为 `media_id` FK，完成 attach、`mark_public`、读时 resolve URL，并禁止删除仍被引用的 media。

## What Changes

- **migration**：`users.avatar_media_id`；`shops.logo_media_id`、`products.primary_media_id`；**删除** `shops.logo_url`、`products.image_url`
- **media 域增强**：修复 DELETE 所有权（`owner_user_id`，非 `can_read`）与 upload `content_type` 硬编码 bug；`GET /media/{id}` JSON 元数据；`assert_owned_by`、`mark_public`、`resolve_urls`、`count_references`；`DELETE /media/{id}` 有业务引用 → **409**
- **user**：`PATCH /users/me` 接受 `avatar_media_id`；`UserResponse` / `GET /users/me` 增加 `avatar_url`（resolve）
- **catalog**：create/patch 接受 `logo_media_id` / `primary_media_id`；响应仍单值 `logo_url` / `image_url`（service 层 resolve）
- **attach 规则**：`media.owner == 操作者`；绑他人 media → **403**；attach 须 `image/*`（422，响应含 `media_id`）；成功 **同事务** `mark_public`
- **engagement**：仅 `get_products_for_engagement` 内部 resolve → `EngagementProduct.image_url`（**DTO 不变**）
- **tests/support**：catalog/user builders 与 helper 改为 upload + media_id；新增 attach / 409 测例

## Non-goals

- **不** 建 `product_media` 关联表（多图留给后续 change）
- **不** 改 `EngagementProduct` schema 字段名
- **不** RAG / Outbox / 孤儿 GC / 缩略图 / CDN / 组合 multipart PATCH
- **不** 生产规范大 refactor

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `media-storage`：`GET /media/{id}` JSON 元数据；`DELETE` 增加引用检查 409；新增 attach 相关 service 方法
- `user-auth`：头像 attach；`avatar_url` 响应
- `catalog-shop`：`logo_media_id` 写路径；`logo_url` 读路径 resolve
- `catalog-products`：`primary_media_id` 写路径；`image_url` 读路径 resolve；`get_products_for_engagement` 内部 resolve

## Impact

- **业务域**：`media`（增强）、`user`、`catalog`；`engagement`（间接，只读 resolve）
- **API**：`GET /media/{id}` 返回元数据 JSON（与 `/file` 二进制分流）；catalog/user 写用 media_id；读仍暴露 url 字符串；**BREAKING** 写请求体（移除 `image_url`/`logo_url`，无生产兼容负担）
- **测试**：`tests/catalog/`、`tests/user/`、helpers/builders 大迁移；`tests/media/test_delete_media.py`（含 public 非 owner 403）、`test_delete_referenced.py`、`test_get_media_metadata.py`
- **依赖**：已合并的 `media-storage`（主 spec `openspec/specs/media-storage/spec.md`）
