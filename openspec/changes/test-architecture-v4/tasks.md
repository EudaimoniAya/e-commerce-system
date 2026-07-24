## 1. 测试环境（APP_ENV_FILE + .env.test）

- [x] 1.1 `app/infra/config.py`：支持 `APP_ENV_FILE`（默认 `.env`）
- [x] 1.2 新增 `.env.test`（JWT、socket DATABASE_URL、TTL=86400 等）；更新 `.env.example` 说明
- [x] 1.3 `Taskfile.yml` 的 `test`/`ci` 设置 `APP_ENV_FILE=.env.test`；`.github/workflows/ci.yml` 同步
- [x] 1.4 跑 `devbox run -- task ci` 确认 §1 行为不变（仍用现有 conftest env，至 §3 前可并存）

## 2. Settings 缓存

> §2 仅新增 `tests/support/env.py` 与减冗余 cache；**删 `ensure_integration_auth_env` 放在 Task 3.4**（与 SAVEPOINT 同批）。

- [x] 2.1 新增 `tests/support/env.py`：`bootstrap_test_env()`（可选，§1 完成后简化 conftest import 前逻辑）
- [x] 2.2 文档化：`cache_clear` 仅允许 `env.py`（design 纪律）

## 3. SAVEPOINT + integration_client（POC 门禁）

- [x] 3.0 **POC**：`db_session` + SAVEPOINT + `get_db` override + `integration_client`；用例「注册→开店→rollback 后 users/shops 无残留」；验证 `login_admin` 可读 migration seed
- [ ] 3.1 `conftest`：`db_session` 注册 override（不 close session）、`integration_client` 依赖 `db_session`；保留 plain `client`
- [ ] 3.2 确认 override 生命周期：`reset_engine` 仅清 app 全局 engine，不 dispose 测试 fixture engine；autouse **保留**
- [ ] 3.3 删除 `app/ordering/service.py` 中 `_get_reservation_ttl()` 的 `os.environ` 分支
- [ ] 3.4 删除 helpers 内全部 `ensure_integration_auth_env`（~14 处）、`conftest` autouse、`tests/infra/test_auth.py`；删除冗余 `configure_integration_test_env` 常量
- [ ] 3.5 grep inventory：`db_session` / `client` / `database_url` / `seed_inactive_user` / `ensure_integration_auth_env` 用法清单

> **Apply 约定**：Task 3.0 POC 通过前不得开始 §5。

## 4. tests/support/db + 懒释放 backdate + seed

- [ ] 4.1 新增 `tests/support/db/ordering.py`（`backdate_order_expires_at`、`get_order_status` 等）
- [ ] 4.2 新增 `tests/support/db/catalog.py`（`get_product_stock` 等）
- [ ] 4.3 迁移 ordering lazy-expire 用例：backdate + DB assert；**删除** `override_order_reservation_ttl` 与 **`wait_past_order_expiry`**
- [ ] 4.4 `seed_inactive_user(session: AsyncSession, ...)`；删独立 `create_async_engine`
- [ ] 4.4a 迁移 `tests/user/test_login.py`：`integration_client` + `db_session` 作用域内 seed
- [ ] 4.4b 迁移 `tests/ordering/test_create_order_by_seller.py` 中 seed 调用
- [ ] 4.5 design/spec 文档化探针例外：`test_admin_seed.py`、`test_readiness.py`、`test_user_summary.py` 不迁移 override

## 5. 单批测试大迁移（integration_client + Pipeline 删除 + helper 分域）

> 约 23–28 个文件；**每个 test 文件本节只 touch 一次**。POC 通过后可在 dedicated 分支集中完成。

- [ ] 5.1 全量 `@integration` HTTP 用例：`client` → `integration_client`（health / 探针例外除外）
- [ ] 5.2 瘦身 `*Context`（`access_token`）；`bearer_headers(token: str)`；Setup fixture 依赖 `integration_client`
- [ ] 5.3 删除 `PipelineResult` / `pipeline.py`；替换全库 `.root.step(...)` 引用
- [ ] 5.4 拆分 `helpers.py` → `auth.py`、`catalog/*`、`ordering/*`；更新 conftest re-export
- [ ] 5.5 更新 `.cursor/rules/test-architecture.mdc`、`docs/decision/测试与数据库策略.md`（SAVEPOINT + 探针例外）
- [ ] 5.6 grep 验收：无 `PipelineResult`、无 `override_order_reservation_ttl`、无 `wait_past_order_expiry`、test 无 `from app.*.repository`

## 6. CI 与收尾

- [ ] 6.1 `devbox run -- task ci` 全绿
- [ ] 6.2 archive 前 sync delta spec 至 `openspec/specs/test-architecture/spec.md`
