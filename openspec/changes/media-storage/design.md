## Context

- `products.image_url`、`shops.logo_url` 为可空 VARCHAR(512) 外链；`users` 无头像列。数据均为测试/fixture，无生产线上存量。
- ADR-001：平台能力可与业务域并列；跨域仅 service + schema。media 归属 **`app/media/`**（非 `infra/`，因具备独立表、路由与 ownership 规则）。
- 集成测试使用 SAVEPOINT + `integration_client`（ADR-003）：MySQL 可回滚，**文件 IO 不在事务内**，测试须注入 `InMemoryBackend` 或隔离临时目录。
- 后续 `media-wire` change 将把业务表改为 `*_media_id` 并 resolve URL；本 change 仅建立 media 对外契约：**给定 media_id，可读元数据摘要与文件流**。

## Goals / Non-Goals

**Goals:**

- 交付可独立演示的 media 平台域：upload → `GET /media/{id}/file` → delete
- MySQL 存 `media_assets` 元数据；字节存 `StorageBackend`；API URL 用 `id`，不用 `storage_key`
- 上传安全链：流式大小限制、白名单、魔数、禁 SVG
- 双 backend：`LocalFilesystemBackend`（dev/CI 可选）、`InMemoryBackend`（integration 默认）
- TDD：spec 场景 → integration + unit 覆盖

**Non-Goals:**

- 业务域 attach、public 切换（attach 时 `mark_public`）、引用检查 DELETE 409
- 元数据 GET、文档类 MIME、GC、缩略图、远程对象存储 backend
- 见 proposal.md Non-goals

## Decisions

### 1. 模块布局

```text
app/media/
├── router.py           # POST /media, GET /media/{id}/file, DELETE /media/{id}
├── service.py          # upload, delete, can_read, get_stream
├── repository.py
├── models.py           # MediaAsset ORM → media_assets
├── schemas.py          # MediaSummary
├── deps.py             # get_storage_backend, get_media_service
└── storage/
    ├── protocol.py     # StorageBackend
    ├── local.py        # LocalFilesystemBackend
    └── memory.py       # InMemoryBackend
```

`app/main.py` 挂载 media router。config 项放 `infra/config.py`（与 DATABASE_URL 同级 env 注入）。

### 2. `media_assets` 表（8 列）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID v4；URL/FK 索引 |
| `owner_user_id` | CHAR(36) FK → users.id | 上传者 |
| `visibility` | VARCHAR(16) | `owner_only` \| `public`；默认 `owner_only` |
| `content_type` | VARCHAR(128) | 魔数检测后的 MIME |
| `size_bytes` | INT | 实际上传大小 |
| `storage_key` | VARCHAR(512) | 相对 storage root 的对象键 |
| `original_filename` | VARCHAR(255) | 展示/下载名；**不参与** storage 路径 |
| `created_at` | DATETIME | |

**不建** `purpose`（读权限由 `visibility` 承担）、`content_hash`、`status`。

**storage_key 生成**：`f"{id[:2]}/{id[2:4]}/{id}"`（两级分片，降低单目录文件数）。`storage_key` 为存储后端对象键；`MEDIA_STORAGE_ROOT` 为部署级根目录（env，非表字段）。

**术语**：

| 名称 | 含义 |
|------|------|
| `id` | 对外 API/FK 索引 |
| `storage_key` | backend 内定位字节的键 |
| `MEDIA_STORAGE_ROOT` | 本地盘根路径（仅 local backend） |
| URL path | `/media/{id}/file`（与 storage 布局无关） |

### 3. 存储抽象与 backend 选择

```python
# 协议（示意）
class StorageBackend(Protocol):
    async def save(self, key: str, data: bytes, content_type: str) -> None: ...
    async def open(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
```

| Backend | 用途 | 理由 |
|---------|------|------|
| `LocalFilesystemBackend` | dev（`.data/media`）、backend 单测（pytest `tmp_path`） | 验证真实 IO、分片路径 |
| `InMemoryBackend` | integration 测试（`integration_client`） | SAVEPOINT 不回滚磁盘；内存随进程丢弃 |

**为何双实现**：integration 必须使用 InMemory 避免测试污染与 flaky；Local 单测独占覆盖落盘路径。**并非**为远程存储预留而强行抽象——远程 backend 若后续需要，再实现第三 backend 并实现同一协议。

**写入顺序与一致性**：

```text
1. 生成 id、storage_key
2. StorageBackend.save(key, stream)   # 先字节
3. INSERT media_assets                # 后元数据
4. commit

若 3 失败：best-effort StorageBackend.delete(key)；极低概率残留 orphan 文件，接受（GC Non-goal）
```

### 4. API 与 visibility

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/media` | Bearer | multipart `file`；201 MediaSummary |
| GET | `/media/{id}/file` | 可选 | `public`→匿名 200；`owner_only`→非 owner 403（或 404，见 spec） |
| DELETE | `/media/{id}` | Bearer owner | 204；非 owner 403；本 change **不** 查业务 FK |

**MediaSummary**：`id`, `url`（`/media/{id}/file`）, `content_type`, `size_bytes`, `created_at`。

本 change 所有 upload 均为 `owner_only`；`public` 枚举与读逻辑实现就绪，供 `media-wire` attach 时调用 `mark_public`。

### 5. 上传校验链

| 步骤 | 规则 |
|------|------|
| 大小 | `media_max_size_bytes`（默认 5MB）；**流式累加**，超限即中断（不信任 Content-Length） |
| 白名单 | `image/jpeg`, `image/png`, `image/webp`；**禁止** `image/svg+xml`（存储型 XSS 面） |
| 魔数 | JPEG `FF D8 FF`；PNG `\x89PNG`；WEBP `RIFF....WEBP` |
| 持久化 MIME | 存魔数结果，非客户端声明 |
| 响应头 | `GET .../file` 返回 `X-Content-Type-Options: nosniff` |

**original_filename**：自 multipart 文件名写入；同 owner 重名允许重复 upload（两条 media 记录）；可选在元数据字段追加 ` (1)` 显示名——**不**影响 storage_key。

### 6. 限速

- 仅 `/media` 路由：Redis 滑动窗口/计数，每 user 每窗口 N 次（可配置，如 60/min）
- 与大小上限共同限制请求洪峰与大 payload 磁盘占用
- 超限 → 429

实现于 media 域（如 `media/rate_limit.py`），不扩展 infra 通用 middleware。

### 7. 跨域边界（本 change）

- **无业务域调用**；media 不 import catalog/user ORM
- `media-wire` 将调用：`assert_owned_by`、`mark_public`、`resolve_urls`、`count_references`（后两者 wire 阶段实现；本 change 可预留 service 方法签名或 wire 再增）

### 8. 部署与 `MEDIA_STORAGE_ROOT`

| 档位 | `MEDIA_STORAGE_BACKEND` | `MEDIA_STORAGE_ROOT` | 持久化 |
|------|-------------------------|----------------------|--------|
| 本地 dev | `local` | `{project}/.data/media`（gitignore） | 是 |
| CI integration | `memory`（测试 override） | N/A | 否 |
| CI backend 单测 | `local` | pytest `tmp_path` | 否 |
| 容器试跑 | `local` | `/app/data/media` | 仅当挂载卷 |

GHCR 镜像构建不嵌入用户上传文件；运行时由 env 决定 root。无生产环境时，dev 使用 `.data/` 作为本地运行时数据目录（与 `.venv` 同类约定，非框架标准）。

### 9. 测试策略

| 层 | Backend | 覆盖 |
|----|---------|------|
| `tests/unit/media/test_storage_local.py` | Local + tmp_path | save/open/delete、分片路径 |
| `tests/unit/media/test_magic_bytes.py` | 无 IO | 魔数、拒 SVG |
| `tests/unit/media/test_visibility.py` | InMemory + service | owner_only / public 读规则 |
| `tests/media/test_*.py` | InMemory（fixture override） | HTTP upload/download/delete、422/403、限速 |

**Support**：`upload_media(client, headers, file_bytes, filename) -> MediaResult`；小 PNG/JPEG fixture bytes 放 `tests/support/fixtures/` 或 helper 内常量。

**integration_client fixture**：为 media 相关测例 override `get_storage_backend` → `InMemoryBackend()`；或通过 env `MEDIA_STORAGE_BACKEND=memory` 在测试 bootstrap 设置。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| upload 后未 attach 的 orphan 文件 | Non-goal GC；wire 前仅 owner 可 DELETE |
| 先写盘后写库失败导致 orphan 字节 | best-effort 补偿 delete；概率低 |
| integration 误用 Local 导致磁盘残留 | 强制 InMemory override + 文档 |
| `owner_only` 文件 URL 被 uuid 猜到 | UUID 空间；visibility 与 id 不可猜性正交 |
| 限速依赖 Redis | CI 已有 redis service；与 SMS OTP 共用实例 |

## Migration Plan

- 单 migration 创建 `media_assets`；**不** 修改业务表
- 无数据回填；rollback drop `media_assets`
- merge 后现有 catalog/user 测试无需改动

## Open Questions

（无阻塞项；以下在 apply 前由 spec 定稿）

- `owner_only` 非 owner 访问返回 **403** 还是 **404**（spec 选一并全库一致）
- 限速 window 与阈值默认值（config 默认即可）
