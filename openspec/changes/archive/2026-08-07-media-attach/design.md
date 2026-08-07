## Context

- `media-storage` 已交付 `app/media/`、`media_assets`、`POST/GET/file/DELETE`（无引用 409、无元数据 GET）、`visibility`（upload 默认 `owner_only`）。
- 业务表仍为 URL 字符串；fixture/测试数据，无生产迁移负担。
- ADR-001：user/catalog 只调 `media.service` + schema，禁止 import media ORM。
- ADR-003：integration 继续 `InMemoryBackend` + SAVEPOINT；attach 测例走 HTTP 全链路。

## Goals / Non-Goals

**Goals:**

- user / catalog 写路径存 `*_media_id`；读路径 resolve 为 `/media/{id}/file`
- attach 时校验 owner + `image/*`；成功 `mark_public`
- `GET /media/{id}` 返回 JSON 元数据（读权限与 `/file` 一致）
- `DELETE /media` 被引用 → 409
- `get_products_for_engagement` 继续返回 `image_url`（内部 resolve）
- TDD：§1 migration → §2 红测 → §3~N 绿

**Non-Goals:**

- 见 proposal.md

## Decisions

### 1. Schema 硬切

| 表 | 删除 | 新增 |
|----|------|------|
| `users` | — | `avatar_media_id` FK → `media_assets.id` NULL |
| `shops` | `logo_url` | `logo_media_id` FK NULL |
| `products` | `image_url` | `primary_media_id` FK NULL |

单商品仍 **1:1 主图**（`primary_media_id`）；不建 `product_media` 表。

### 2. media 元数据 vs 二进制

| 端点 | 返回 | 鉴权 |
|------|------|------|
| `GET /media/{id}` | JSON 元数据 | JWT 可选；`can_read` 同 `/file` |
| `GET /media/{id}/file` | 二进制流 | 同上 |

**`GET /media/{id}` 响应体**（`MediaDetail`，跨域 DTO）：

| 字段 | 说明 |
|------|------|
| `id` | UUID |
| `url` | 相对路径 `/media/{id}/file`（与 `resolve_urls` 一致） |
| `content_type` | 魔数检测 MIME |
| `size_bytes` | 字节数 |
| `visibility` | `public` \| `owner_only` |
| `original_filename` | 上传时文件名（可空） |
| `created_at` | ISO8601 |

**不暴露** `storage_key`、`owner_user_id`。404 不存在；`owner_only` 且非 owner → 403。

`POST /media` 仍返回 `MediaSummary`（5 字段）；`GET /media/{id}` 返回 `MediaDetail`（含 `visibility`、`original_filename`）。

### 3. 业务 API 形状（读写分离）

| 域 | 写（请求） | 读（响应） |
|----|-----------|-----------|
| user | `PATCH /users/me` `{ avatar_media_id? }` | `avatar_url` |
| shop | `logo_media_id?` on create/patch | `logo_url` |
| product | `primary_media_id?` on create/patch | `image_url` |

响应 url 由 `media.service.resolve_urls(ids) -> dict[id, url]` 填充；缺失 media 行 → 对应 url 字段 `null`。

### 4. Attach 流程（分步，与 storage 一致）

```text
POST /media → media_id（owner_only）
PATCH/POST 业务 body 带 *_media_id
  → media.assert_owned_by(media_id, current_user_id)  # 403
  → media.assert_image_content_type(media_id)         # 422 + media_id
  → 写业务 FK（同事务）
  → media.mark_public(media_id)
```

商品/店 logo：操作者须为 shop owner（catalog 域鉴权后再调 media assert）。

**`assert_image_content_type` 422 响应**（符合 `infra-api-errors` envelope；`message` 须含 `media_id` 以便客户端定位）：

```json
{
  "error": {
    "code": "INVALID_MEDIA_TYPE",
    "message": "Media {media_id} content_type must be image/*",
    "request_id": "..."
  }
}
```

实现：`HTTPException(status_code=422, detail={"code": "INVALID_MEDIA_TYPE", "message": f"Media {media_id} content_type must be image/*"})`。

### 5. media.service 新增方法

| 方法 | 职责 |
|------|------|
| `get_detail(media_id, optional_user_id) -> MediaDetail` | 元数据；`can_read` 不通过 → 403；不存在 → 404 |
| `assert_owned_by(media_id, user_id)` | 404 不存在；403 非 owner |
| `assert_image_content_type(media_id)` | 非 `image/*` → 422 |
| `mark_public(media_id)` | `visibility = public` |
| `resolve_urls(media_ids) -> dict[str, str]` | 批量 id → `/media/{id}/file` |
| `count_references(media_id) -> int` | 查 users/shops/products FK |

`count_references` 实现于 media 域（只读 SQL 查三表），**不** import catalog/user ORM（可用 text SQL 或独立 query module）。

### 6. DELETE 所有权与 409

**所有权**：DELETE SHALL 比较 `asset.owner_user_id == current_user_id`。**禁止**使用 `can_read`——`can_read` 对 `visibility=public` 对任意用户返回 True（读权限语义），attach 后业务 media 均为 public，误用会导致非 owner 可删他人 media。

```text
DELETE /media/{id}
  → owner_user_id == current_user_id（403 否则）
  → count_references > 0 → 409
  → 否则删 DB + storage
```

**upload content_type**：`POST /media` router SHALL 将 `validate_media_upload()` 返回的真实 MIME 传入 `MediaService.upload(content_type=...)`；禁止 service 内硬编码 `image/png`（否则 GET 元数据与 `/file` 的 `Content-Type` 错误）。

### 7. engagement 路径

```text
get_products_for_engagement:
  repository 批量查 product.primary_media_id
  resolve_urls → 填 EngagementProduct.image_url
```

DTO 与 engagement 域 **零改动**。

### 8. 跨域 import

```python
# 允许
from app.media.service import MediaService  # 或模块级函数
from app.media.schemas import MediaSummary

# 禁止
from app.media.models import MediaAsset
from app.media.repository import MediaRepository
```

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| helpers 大迁移导致 CI 红面广 | §1 migration 后 §2 集中写红测；按域分批绿 |
| 换绑 media 后旧 media 仍为 public | **无自动回退**；旧 media 保持 `visibility=public`，任何人仍可 GET；用户如需撤销访问应手动 DELETE 未引用 media |
| 换绑 media 后旧 media 变 orphan | Non-goal GC；owner 可 DELETE 未引用 media |
| resolve N+1 | 列表路径 batch `resolve_urls` |
| DELETE 409 TOCTOU 竞态 | `count_references==0` 与 DELETE 提交之间可能被 attach；个人项目低并发，接受；不在本 change 加锁 |

## Migration Plan

- 单 migration：加 FK 列、drop URL 列；无数据回填（测试 fixture 改 upload）
- rollback：恢复 URL 列（开发环境；非生产关注点）

## Open Questions

（无阻塞项。）
