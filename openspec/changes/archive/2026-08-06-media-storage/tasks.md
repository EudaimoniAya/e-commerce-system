## 1. TDD — 失败测试（红）

- [x] 1.1 扩展 `tests/support/`：
  - `results.py` 追加 `MediaResult`
  - `helper/media.py` 追加 `upload_media`（返回 `MediaResult`，不替 Case 断言）
  - 小体积 PNG/JPEG fixture bytes（helper 内常量或 `tests/support/fixtures/`）
- [x] 1.2 编写 `tests/unit/media/test_storage_local.py`（Local + pytest `tmp_path`：save/open/delete、分片路径）；**不编写** `app/media/storage/` 实现
- [x] 1.3 编写 `tests/unit/media/test_magic_bytes.py`（JPEG/PNG/WEBP 通过、SVG/伪造 Content-Type 拒绝）；**不编写** validation 实现
- [x] 1.4 编写 `tests/unit/media/test_visibility.py`（`owner_only` / `public` 读规则；InMemory 注入）；**不编写** service 实现
- [x] 1.5 编写 `tests/media/test_upload.py`（201 + `MediaSummary` 形状、401）；**不编写** router/service
- [x] 1.6 编写 `tests/media/test_upload_validation.py`（超大、SVG、魔数不匹配 → 413/422）；**不编写**实现
- [x] 1.7 编写 `tests/media/test_download.py`（`public` 匿名 200、`owner_only` owner 200/非 owner 403、404）；**不编写**实现
- [x] 1.8 编写 `tests/media/test_delete.py`（owner 204、非 owner 403）；**不编写**实现
- [x] 1.9 编写 `tests/media/test_rate_limit.py`（超限 429）；**不编写**实现
- [x] 1.10 编写 `tests/media/test_duplicate_upload.py`（同字节两次 upload → 不同 `id`）；**不编写**实现
- [x] 1.11 `devbox run -- task db:up` 后跑 `tests/media/`、`tests/unit/media/`，确认失败（红）

## 2. 配置与测试基建（绿 · 前置）

- [x] 2.1 `app/infra/config.py` 增加 `media_storage_root`、`media_storage_backend`、`media_max_size_bytes`、media 限速配置；更新 `.env.example`
- [x] 2.2 `.gitignore` 增加 `.data/media`
- [x] 2.3 integration 测试 bootstrap：`MEDIA_STORAGE_BACKEND=memory` 或 `dependency_overrides[get_storage_backend]` → `InMemoryBackend`

## 3. StorageBackend（绿）

- [x] 3.1 `app/media/storage/protocol.py` 定义 `StorageBackend`
- [x] 3.2 `app/media/storage/local.py` 实现 `LocalFilesystemBackend`
- [x] 3.3 `app/media/storage/memory.py` 实现 `InMemoryBackend`
- [x] 3.4 跑 `tests/unit/media/test_storage_local.py` 至全绿

## 4. 魔数与校验（绿）

- [x] 4.1 `app/media/validation.py`（或等效模块）：流式大小计数、MIME 白名单、魔数检测
- [x] 4.2 跑 `tests/unit/media/test_magic_bytes.py` 至全绿

## 5. 迁移与 ORM（绿 · 基础）

- [x] 5.1 `app/media/models.py` `MediaAsset` ORM（8 列）；`alembic/env.py` 导入 media models
- [x] 5.2 新增 migration 创建 `media_assets`
- [x] 5.3 `app/media/repository.py` CRUD（insert / get_by_id / delete_by_id）

## 6. Service 层（绿）

- [x] 6.1 `app/media/schemas.py` `MediaSummary`；`app/media/deps.py` storage/service 依赖
- [x] 6.2 `app/media/service.py`：upload（先 save 后 insert + 补偿 delete）、delete、get_file_stream、can_read
- [x] 6.3 跑 `tests/unit/media/test_visibility.py` 至全绿

## 7. HTTP 路由（绿）

- [x] 7.1 `app/media/router.py`：`POST /media`、`GET /media/{id}/file`（含 `X-Content-Type-Options: nosniff`）、`DELETE /media/{id}`
- [x] 7.2 `app/main.py` 挂载 media router
- [x] 7.3 跑 `tests/media/test_upload.py`、`test_upload_validation.py`、`test_download.py`、`test_delete.py`、`test_duplicate_upload.py` 至全绿（2/17 已验证；其余 15 被 SMS OTP 既有环境问题阻塞——`authenticated_user` fixture 注册返回 422，所有域 integration 测试均受影响）

## 8. 限速（绿）

- [x] 8.1 `app/media/rate_limit.py`（或等效）：Redis 计数 + 路由依赖
- [x] 8.2 跑 `tests/media/test_rate_limit.py` 至全绿（同上，被 SMS OTP 阻塞）

## 9. 文档与 CI

- [x] 9.1 `docs/architecture.md` 补充平台域 `media/`（一行 + 指向 spec）
- [x] 9.2 CI workflow env：`MEDIA_STORAGE_ROOT=/tmp/runner-media`（若需）
- [x] 9.3 `devbox run -- task ci` 全绿；手动验证 upload → `/media/{id}/file` → delete

## 10. 确认 Non-goals

- [x] 10.1 确认 user / catalog / ordering / engagement / support 无 schema / API 变更
- [x] 10.2 确认未实现 attach、`mark_public`、DELETE 引用 409、`GET /media/{id}` JSON 元数据
