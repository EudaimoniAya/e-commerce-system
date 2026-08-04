# media-storage Specification (delta)

## ADDED Requirements

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

上传 SHALL 按序校验：（1）流式累计大小不超过 `media_max_size_bytes`（默认 5MB），超限 SHALL 413 或 422；（2）最终 MIME SHALL 属于 `image/jpeg`、`image/png`、`image/webp`；（3）SHALL 魔数校验文件头，不信任客户端 Content-Type；（4）持久化 `content_type` SHALL 为魔数结果；（5）SHALL 拒绝 `image/svg+xml` 及魔数不匹配文件。

#### Scenario: Oversized upload rejected

- **WHEN** 已登录用户上传超过 `media_max_size_bytes` 的文件
- **THEN** 响应 status SHALL 为 413 或 422
- **AND** SHALL NOT 创建 `media_assets` 行

#### Scenario: SVG upload rejected

- **WHEN** 已登录用户上传 SVG 或魔数为 SVG 的文件
- **THEN** 响应 status SHALL 为 422
- **AND** SHALL NOT 创建 `media_assets` 行

#### Scenario: Spoofed content-type rejected

- **WHEN** 已登录用户上传非图片魔数但声明 `Content-Type: image/jpeg`
- **THEN** 响应 status SHALL 为 422

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

### Requirement: Delete media by owner

系统 SHALL 提供 `DELETE /media/{id}`，要求 Bearer JWT。仅 `owner_user_id` 匹配 SHALL 可删除。成功 SHALL 返回 204 并删除 DB 行与 storage 字节。非 owner SHALL 403。本 change SHALL NOT 检查业务表 FK 引用。

#### Scenario: Owner deletes unattached media

- **WHEN** owner DELETE 其上传的 media
- **THEN** 响应 status SHALL 为 204
- **AND** 后续 GET `/media/{id}/file` SHALL 404

#### Scenario: Non-owner delete forbidden

- **WHEN** 其他用户 DELETE 该 media
- **THEN** 响应 status SHALL 为 403
- **AND** `media_assets` 行 SHALL 仍存在

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
