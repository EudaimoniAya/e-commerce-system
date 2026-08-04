## Why

电商底座（user / catalog / ordering / engagement / support）已就绪，但商品图与店铺 logo 仍为 `VARCHAR(512)` 外链字段，用户无头像存储；文件字节不在系统内管理。在业务域接入 `media_id` 引用（后续 `media-wire` change）之前，需先交付 **media 平台域存储能力**：统一上传、按 id 取流、所有权与读权限、本地存储抽象与测试隔离。当前环境无生产线上数据，可对 schema 与 API 做硬切而不需兼容迁移。

本 change（`media-storage`）仅交付 media 域可独立演示闭环；**不修改** user / catalog 等业务表与 API。

## What Changes

- 新增 **`app/media/`** 平台域（router → service → repository → model + schemas + storage）
- 新增 **`media_assets`** 表与 Alembic migration
- 新增 **`StorageBackend`** 协议及 **`LocalFilesystemBackend`**、**`InMemoryBackend`** 实现
- 新增 API：
  - `POST /media`（multipart，JWT）→ 201 `MediaSummary`
  - `GET /media/{id}/file` → 二进制流（相对 URL `/media/{id}/file`）
  - `DELETE /media/{id}` → 仅 owner；**无**跨表引用检查（留给 `media-wire`）
- 上传校验：大小上限（流式计数）、图片 MIME 白名单、魔数检测、禁 SVG；响应头 `X-Content-Type-Options: nosniff`
- **`visibility`**：`owner_only`（默认）| `public`；本 change 不实现 attach 时的 `mark_public`（上传后均为 `owner_only`）
- media 路由 **Redis 限速**（项目已有 Redis；不建 infra 通用限流）
- **`app/infra/config.py`** 增加 `media_storage_root`、`media_storage_backend`、`media_max_size_bytes`、限速相关配置
- 测试：`tests/media/` integration、`tests/unit/media/` backend/校验单测、`tests/support/helper/media.py`（`upload_media` → `MediaResult`）
- CI：`MEDIA_STORAGE_ROOT` 指向 runner 临时目录；integration 注入 `InMemoryBackend`（SAVEPOINT 不回滚文件）
- 文档：本 change OpenSpec 产物；`architecture.md` 平台域 media 一行（apply 阶段）

## Non-goals

- **不** 修改 user / catalog / ordering / engagement / support 业务 schema 或 HTTP 契约（`image_url` / `logo_url` 等保持现状）
- **不** 实现业务 attach、`mark_public` 批量 resolve、DELETE 引用 409（`media-wire` change）
- **不** 实现 `GET /media/{id}` JSON 元数据端点（`/file` 后缀为后续预留）
- **不** 实现 RAG 文档类型、Outbox、ingestion worker
- **不** 孤儿文件 GC、缩略图、CDN、客户端直传、SVG、content_hash 去重
- **不** 实现 infra 通用 HTTP 限流 middleware
- **不** 引入对象存储远程 backend（仅本地抽象 + 内存实现；远程 backend 为后续 change）

## Capabilities

### New Capabilities

- `media-storage`: media 平台域上传/下载/删除、`media_assets` 持久化、`StorageBackend` 双实现、校验链、visibility、media 专属限速

### Modified Capabilities

（无。业务域 spec 在本 change 不变。）

## Impact

- **业务域**: **media**（新建）；**infra**（config 扩展）；user / catalog / ordering / engagement / support **无行为变更**
- **新增/修改文件**: `app/media/**`、`app/infra/config.py`、`app/main.py`（挂载 router）、`alembic/versions/*media*`、`tests/media/`、`tests/unit/media/`、`tests/support/helper/media.py`、`tests/support/results.py`（`MediaResult`）、`.gitignore`（`.data/media`）、`.github/workflows/test.yaml`（env，若需）
- **API**: 新增 `/media` 前缀端点；现有业务 API 不变
- **依赖**: 无新增第三方包（复用 Redis、现有 multipart 栈）
