# media-storage Specification

## Purpose

media 平台域 — 统一媒体文件上传、按 id 取流、所有权与读权限控制、本地存储抽象与测试隔离。本 capability 交付后可独立演示：upload → `GET /media/{id}/file` → delete。

## Requirements

### Requirement: media_assets table schema

系统 SHALL 持久化 `media_assets` 表，列 SHALL 包含：`id`（UUID PK）、`owner_user_id`（FK → `users.id`）、`visibility`（`public` | `owner_only`，默认 `owner_only`）、`content_type`、`size_bytes`、`storage_key`、`original_filename`、`created_at`。`storage_key` SHALL 为相对 storage root 的对象键，格式 SHALL 为 `{id 前 2 hex}/{第 3–4 hex}/{完整 id}`。

#### Scenario: Migration creates media_assets

- **WHEN** 执行 Alembic upgrade head
- **THEN** 数据库 SHALL 存在 `media_assets` 表且含上述列

### Requirement: StorageBackend dual implementation

系统 SHALL 提供 `StorageBackend` 协议，含 `save`、`open`、`delete`。SHALL 提供 `LocalFilesystemBackend`（读写 `MEDIA_STORAGE_ROOT` 下 `storage_key`）与 `InMemoryBackend`（进程内字典）。运行时 SHALL 通过配置 `media_storage_backend`（`local` | `memory`）选择实现。

#### Scenario: Local backend round-trip

- **WHEN** `LocalFilesystemBackend` 对 key `aa/bb/{uuid}` 执行 save 后 open
- **THEN** open SHALL 返回与 save 相同的字节

#### Scenario: Memory backend isolation

- **WHEN** 测试注入 `InMemoryBackend` 并 upload 文件
- **THEN** SHALL NOT 在 `MEDIA_STORAGE_ROOT` 磁盘路径创建文件

### Requirement: Upload media file

系统 SHALL 提供 `POST /media`（`multipart/form-data`，字段 `file`），要求 Bearer JWT。任意已登录用户 SHALL 可上传。成功 SHALL 返回 201 与 JSON `MediaSummary`：`id`、`url`（`/media/{id}/file`）、`content_type`、`size_bytes`、`created_at`。新行 `visibility` SHALL 为 `owner_only`，`owner_user_id` SHALL 为 JWT sub。

#### Scenario: Authenticated upload succeeds

- **WHEN** 已登录用户 POST 合法 PNG（≤ 配置大小上限）
- **THEN** 响应 status SHALL 为 201
- **AND** 响应体 SHALL 含 `url` 等于 `/media/{id}/file`（与 `id` 一致）
- **AND** `media_assets` SHALL 存在对应行

#### Scenario: Unauthenticated upload rejected

- **WHEN** 无 Authorization 头 POST `/media`
- **THEN** 响应 status SHALL 为 401

### Requirement: Upload validation chain

上传 SHALL 按序校验：（1）`file.size` 预检不超过 `media_max_size_bytes`（默认 5MB），超限 SHALL 413；（2）最终 MIME SHALL 属于 `image/jpeg`、`image/png`、`image/webp`；（3）SHALL 魔数校验文件头，不信任客户端 Content-Type；（4）持久化 `content_type` SHALL 为魔数检测结果，router SHALL 将检测结果传入 `MediaService.upload()`（**禁止** service 硬编码 MIME）；（5）SHALL 拒绝 `image/svg+xml` 及魔数不匹配文件。

#### Scenario: Oversized upload rejected

- **WHEN** 已登录用户上传超过 `media_max_size_bytes` 的文件
- **THEN** 响应 status SHALL 为 413
- **AND** SHALL NOT 创建 `media_assets` 行

#### Scenario: SVG upload rejected

- **WHEN** 已登录用户上传 SVG 或魔数为 SVG 的文件
- **THEN** 响应 status SHALL 为 422
- **AND** SHALL NOT 创建 `media_assets` 行

#### Scenario: Spoofed content-type rejected

- **WHEN** 已登录用户上传非图片魔数但声明 `Content-Type: image/jpeg`
- **THEN** 响应 status SHALL 为 422

#### Scenario: Persisted content_type matches magic number

- **WHEN** 用户 upload 魔数为 JPEG 的文件
- **THEN** `media_assets.content_type` SHALL 为 `image/jpeg`
- **AND** `GET /media/{id}` 响应 `content_type` SHALL 为 `image/jpeg`

### Requirement: Download media file stream

系统 SHALL 提供 `GET /media/{id}/file`，返回二进制流，`Content-Type` SHALL 为库中 `content_type`，SHALL 含响应头 `X-Content-Type-Options: nosniff`。

#### Scenario: Public file anonymous read

- **WHEN** `media_assets.visibility` 为 `public` 且无 Authorization 请求 GET `/media/{id}/file`
- **THEN** 响应 status SHALL 为 200
- **AND** 响应 body SHALL 为原始字节

#### Scenario: Owner-only file rejects non-owner

- **WHEN** `visibility` 为 `owner_only` 且请求者非 `owner_user_id`（含匿名）
- **THEN** 响应 status SHALL 为 403

#### Scenario: Owner-only file allows owner

- **WHEN** `visibility` 为 `owner_only` 且 Bearer 对应 `owner_user_id`
- **THEN** 响应 status SHALL 为 200

#### Scenario: Missing media returns not found

- **WHEN** GET 不存在的 `{id}/file`
- **THEN** 响应 status SHALL 为 404

### Requirement: Get media metadata by id

系统 SHALL 提供 `GET /media/{id}`，返回 **JSON 元数据**（非二进制）。JWT 可选；读权限 SHALL 与 `GET /media/{id}/file` 相同（`visibility=public` 匿名可读；`owner_only` 仅 owner 可读）。响应体 SHALL 包含 `id`、`url`（相对路径 `/media/{id}/file`）、`content_type`、`size_bytes`、`visibility`、`original_filename`、`created_at`。SHALL NOT 暴露 `storage_key` 或 `owner_user_id`。不存在 → **404**；无读权限 → **403**。

#### Scenario: Public media metadata readable anonymously

- **WHEN** 匿名 GET 已 `mark_public`（`visibility=public`）的 media
- **THEN** 响应 status SHALL 为 200
- **AND** body SHALL 含 `id`、`url`、`content_type`、`size_bytes`、`visibility`、`created_at`
- **AND** `url` SHALL 为 `/media/{id}/file`

#### Scenario: Owner-only media requires owner

- **WHEN** 匿名或非 owner GET `visibility=owner_only` 的 media
- **THEN** 响应 status SHALL 为 403

#### Scenario: Owner reads owner-only metadata

- **WHEN** owner GET 其 `owner_only` media
- **THEN** 响应 status SHALL 为 200
- **AND** body SHALL 含完整元数据字段

#### Scenario: Missing media metadata not found

- **WHEN** GET 不存在的 media id
- **THEN** 响应 status SHALL 为 404

### Requirement: Delete media by owner

系统 SHALL 提供 `DELETE /media/{id}`，要求 Bearer JWT。仅 `owner_user_id` 与当前用户匹配 SHALL 可删除（SHALL 直接比较 owner，**SHALL NOT** 使用 `can_read` 判定删除权限）。若 `media_id` 被 `users.avatar_media_id`、`shops.logo_media_id` 或 `products.primary_media_id` 引用，SHALL 返回 **409** 且不删除。无引用时成功 SHALL 返回 204 并删除 DB 行与 storage 字节。非 owner SHALL 403（含 `visibility=public` 的 media）。

#### Scenario: Owner deletes unattached media

- **WHEN** owner DELETE 其上传且未被业务表引用的 media
- **THEN** 响应 status SHALL 为 204
- **AND** 后续 GET `/media/{id}/file` SHALL 404

#### Scenario: Non-owner delete forbidden

- **WHEN** 其他用户 DELETE 该 media
- **THEN** 响应 status SHALL 为 403
- **AND** `media_assets` 行 SHALL 仍存在

#### Scenario: Non-owner cannot delete public media

- **WHEN** 非 owner 的已认证用户 DELETE 一个 `visibility=public` 的 media
- **THEN** 响应 status SHALL 为 403
- **AND** `media_assets` 行与 storage 字节 SHALL 仍存在

#### Scenario: Referenced media delete conflict

- **WHEN** owner DELETE 的 media_id 被任一业务 FK 引用
- **THEN** 响应 status SHALL 为 409
- **AND** `media_assets` 行与 storage 字节 SHALL 仍存在

### Requirement: Media route rate limiting

`/media` 前缀路由 SHALL 对每 authenticated user 实施 Redis 计数限速（窗口与阈值可配置）。超限 SHALL 返回 429。

#### Scenario: Rate limit exceeded

- **WHEN** 同一用户在配置窗口内超过允许次数 POST `/media`
- **THEN** 响应 status SHALL 为 429

### Requirement: Media domain cross-domain import discipline

`app/media/` SHALL NOT import 任何业务域（user/catalog/ordering/engagement/support）的 ORM 或 repository。业务域在本 change SHALL NOT 修改；后续 change 仅允许 `from app.media.service import ...` 与 `from app.media.schemas import ...`。

#### Scenario: No business schema change in media-storage

- **WHEN** 本 change 合并完成
- **THEN** `products`/`shops`/`users` 表结构 SHALL 与 change 前一致（无 `*_media_id` 列变更）

### Requirement: Duplicate bytes are separate records

相同字节多次 upload SHALL 产生多条 `media_assets` 记录（不去重）。`original_filename` MAY 重复；storage_key SHALL 仅依赖各自 `id`。

#### Scenario: Second upload same bytes new id

- **WHEN** 同一用户两次 upload 相同 PNG 文件
- **THEN** 两次响应 `id` SHALL 不同
- **AND** SHALL 存在两条 `media_assets` 行

### Requirement: Media attach service methods

media 域 SHALL 通过 **service**（非 repository 对外）提供 attach 支撑方法，供 user/catalog 调用：`assert_owned_by(media_id, user_id)`、`assert_image_content_type(media_id)`、`mark_public(media_id)`、`resolve_urls(media_ids: list[str]) -> dict[str, str]`、`count_references(media_id) -> int`。业务域 SHALL NOT import media ORM 或 repository。

#### Scenario: resolve_urls returns file paths

- **WHEN** catalog 调用 `resolve_urls` 传入存在的 media id 列表
- **THEN** 返回 dict SHALL 映射每个 id 到 `/media/{id}/file`

#### Scenario: mark_public updates visibility

- **WHEN** attach 成功后调用 `mark_public(media_id)`
- **THEN** 对应行 `visibility` SHALL 为 `public`

#### Scenario: count_references detects FK references

- **WHEN** `media_id` 被 `users.avatar_media_id`、`shops.logo_media_id` 或 `products.primary_media_id` 任一引用
- **THEN** `count_references(media_id)` SHALL 返回 >= 1

#### Scenario: count_references returns zero for unattached media

- **WHEN** `media_id` 未被任何业务表 FK 引用
- **THEN** `count_references(media_id)` SHALL 返回 0

### Requirement: MediaAsset product association

系统 SHALL 在 `media_assets` 表新增 `product_id`（UUID，可空，**无外键约束**，普通列 + 索引），经 media 域 migration 管理；**SHALL NOT** 引入 FK 以避免阻塞商品侧生命周期（商品无 DELETE 路径，且外键 RESTRICT 会干扰未来演进）。

#### Scenario: 上传商品文档写入关联（仅格式校验）

- **WHEN** 商家上传商品相关文档且指定关联商品
- **THEN** `MediaAsset` 行 SHALL 记录 `product_id`
- **AND** media service SHALL 仅校验 `product_id` 为合法 UUID（格式错误返回 4xx）；**SHALL NOT** 跨域校验 product 存在性（media 不依赖 catalog——catalog→media 依赖已存在，反向校验会成环）

#### Scenario: product 存在性校验由 ai 域承担

- **WHEN** ai 域 `reindex_shop` 拉取商品文档时发现 `product_id` 不存在或商品未上架
- **THEN** SHALL 跳过该 document 并计入 `ReindexStats`（复用 orphan/无效文档清理语义，不阻塞整店 reindex）

#### Scenario: 未关联附件可空

- **WHEN** 上传非商品文档（如头像、通用素材）
- **THEN** `product_id` SHALL 为 NULL，不影响既有 media 行为

### Requirement: Product-scoped document read interface

media 域 SHALL 提供按 `product_id` 查询商品文档列表的只读接口（返回 `MediaAsset` 元数据 + 存储键），供 ai 域 indexing 拉取解析；**SHALL NOT** 暴露给 ai 域底层 storage 内部对象。**media 接口为纯 `product_id` 查询，不做店级过滤**（`MediaAsset` 无 `shop_id`，见 design D3）——店级隔离由 ai 侧 catalog 已上架商品列表保证（ADR-011 §6 校验沿消费方向）。

#### Scenario: ai reindex 拉取商品文档

- **WHEN** ai 域 `reindex_shop(shop_id)` 执行
- **THEN** SHALL 先经 catalog 获取该店已上架商品列表，再按各 `product_id` 经 media 只读接口获取关联文档（含 `asset_id`、`content_type`、`storage_key`、`original_filename`）
- **AND** media 接口 SHALL NOT 接收或依赖 `shop_id`（无店级过滤能力）

### Requirement: Single-asset existence query for orphan cleanup

media 域 SHALL 提供按 `asset_id` 查询单个附件的能力（复用既有单资产查询/详情接口），供 ai 域 reindex orphan 扫描校验「附件是否仍存在」；MVP **SHALL NOT** 新增批量接口（逐条查询，N 次调用可接受，见 design Open Questions）。

#### Scenario: orphan 校验附件存在性

- **WHEN** ai 域 `reindex_shop` 从 PG 反枚举 `document_id`（`source_kind=media_document`）且需校验附件是否仍存在
- **THEN** SHALL 经 media 单资产查询接口逐条校验；附件不存在（404）→ 删除对应 chunk 行

### Requirement: No chunk cleanup call from media

media 域 **SHALL NOT** import ai 域或调用 ai service（含 `delete_document_chunks`）——业务域不依赖 ai（CLAUDE.md 跨域纪律）。附件删除后的 chunk 清理 **SHALL** 由 ai 域 reindex 语义承担（`ai:reindex-shop` 扫 orphan / 商品级 reindex 时校验文档存在性，见 ai-rag-indexing spec）。

#### Scenario: media 无 ai 依赖

- **WHEN** 检查 media 域模块 import
- **THEN** SHALL NOT import `app.ai` 任何模块

#### Scenario: 删附件后 orphan 由 reindex 兜底

- **WHEN** 商家删除已关联商品的附件后执行 `ai:reindex-shop`
- **THEN** PG `product_embedding_chunks` SHALL NOT 含已删除附件的 `document_id` 行
