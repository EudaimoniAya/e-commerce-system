## 1. migration（红测前置）

- [ ] 1.1 Alembic：`users.avatar_media_id`；`shops.logo_media_id` + drop `logo_url`；`products.primary_media_id` + drop `image_url`
- [ ] 1.2 更新 user/catalog ORM models

## 2. TDD — 失败测试（红）

> migration + ORM 已就绪；service/router 尚未接入 → 测试因**行为不匹配**失败（非 AttributeError）。

- [ ] 2.1 更新 `tests/support/builders.py`：`build_shop_create` / `build_product_create` 用 `logo_media_id` / `primary_media_id`，移除 `logo_url` / `image_url`
- [ ] 2.2 更新 `tests/support/helper/catalog.py`：create_shop / create_product 编排 `upload_media` + media_id（或接受显式 media_id 参数）
- [ ] 2.3 编写 `tests/user/test_avatar_attach.py`（attach 200 + avatar_url、403 绑他人、422 非 image、清空 null、公开 GET）；**不编写** user/media attach 实现
- [ ] 2.4 编写/更新 `tests/catalog/test_shop_media.py`、`tests/catalog/test_product_media.py`（logo/主图 attach、403、422、响应 url）；**不编写** catalog 实现
- [ ] 2.5 编写 `tests/media/test_get_media_metadata.py`（public 匿名 200、owner_only 403/200、404）；**不编写** `GET /media/{id}` 实现
- [ ] 2.6 编写/更新 `tests/media/test_delete_media.py`：非 owner DELETE public media → 403；编写 `tests/media/test_delete_referenced.py`（avatar/logo/product 引用 → 409）；**不编写** 修复与 count_references
- [ ] 2.7 更新 `tests/unit/catalog/test_engagement_product_service.py`（row 含 `primary_media_id`、mock resolve → image_url）；**不编写** service 改动
- [ ] 2.8 `devbox run -- task db:up` 后跑上述新增/变更测例，确认失败（红）

## 3. media 域 bugfix + 增强（绿）

> **前置 bugfix**（media-storage 遗留，attach 前必须修）：DELETE 所有权、`content_type` 硬编码。

- [ ] 3.1 **bugfix**：`DELETE /media/{id}` 改为比较 `owner_user_id == current_user_id`（**禁止**用 `can_read` 做所有权校验）
- [ ] 3.2 **bugfix**：`MediaService.upload()` 接受 router 传入的 `content_type`（`validate_media_upload` 返回值，禁止硬编码 `image/png`）
- [ ] 3.3 新增 `MediaDetail` schema；实现 `get_detail` 与 `GET /media/{id}` 路由
- [ ] 3.4 实现 `assert_owned_by`、`assert_image_content_type`、`mark_public`、`resolve_urls`、`count_references`
- [ ] 3.5 `DELETE /media/{id}` 引用检查 → 409
- [ ] 3.6 跑 `tests/media/test_delete_media.py`、`test_get_media_metadata.py`、`test_delete_referenced.py` 至全绿

## 4. user wire（绿）

- [ ] 4.1 `user` schemas/service/router：`avatar_media_id` 写、`avatar_url` 读
- [ ] 4.2 跑 `tests/user/test_avatar_attach.py` 至全绿

## 5. catalog wire（绿）

- [ ] 5.1 shop：create/patch `logo_media_id`；响应 `logo_url` resolve
- [ ] 5.2 product：create/patch `primary_media_id`；响应 `image_url` resolve；列表/公开路径 batch resolve
- [ ] 5.3 `get_products_for_engagement` 内部 resolve
- [ ] 5.4 跑 catalog 相关测例 + `test_engagement_product_service` 至全绿

## 6. 回归与文档

- [ ] 6.1 跑全量 `tests/engagement/` 确认 favorites/browse enrichment 仍绿
- [ ] 6.2 更新 `docs/architecture.md`（业务表 media FK + attach 摘要）
- [ ] 6.3 `devbox run -- task ci` 全绿

## 7. 确认 Non-goals

- [ ] 7.1 确认无 `product_media` 表、无 `EngagementProduct` 字段改名
- [ ] 7.2 确认无 RAG / GC
