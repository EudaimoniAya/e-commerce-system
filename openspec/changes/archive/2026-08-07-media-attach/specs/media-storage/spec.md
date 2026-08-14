# media-storage (delta)

## MODIFIED Requirements

### Requirement: Upload validation chain

上传 SHALL 按序校验：（1）`file.size` 预检不超过 `media_max_size_bytes`（默认 5MB），超限 SHALL 413；（2）最终 MIME SHALL 属于 `image/jpeg`、`image/png`、`image/webp`；（3）SHALL 魔数校验文件头，不信任客户端 Content-Type；（4）持久化 `content_type` SHALL 为魔数检测结果，router SHALL 将检测结果传入 `MediaService.upload()`（**禁止** service 硬编码 MIME）；（5）SHALL 拒绝 `image/svg+xml` 及魔数不匹配文件。

#### Scenario: Persisted content_type matches magic number

- **WHEN** 用户 upload 魔数为 JPEG 的文件
- **THEN** `media_assets.content_type` SHALL 为 `image/jpeg`
- **AND** `GET /media/{id}` 响应 `content_type` SHALL 为 `image/jpeg`

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

## ADDED Requirements

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
