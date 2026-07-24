## 1. 测试环境（APP_ENV_FILE + .env.test）

- [x] 1.1 `app/infra/config.py`：支持 `APP_ENV_FILE`（默认 `.env`）
- [x] 1.2 新增 `.env.test`（JWT、socket DATABASE_URL、TTL=86400 等）；更新 `.env.example` 说明
- [x] 1.3 `Taskfile.yml` 的 `test`/`ci` 设置 `APP_ENV_FILE=.env.test`；`.github/workflows/ci.yml` 同步
- [x] 1.4 跑 `devbox run -- task ci` 确认 §1 行为不变（仍用现有 conftest env，至 §3 前可并存）

## 2. Settings 缓存

> §2 仅新增 `tests/support/utils.py` 与减冗余 cache；**删 `ensure_integration_auth_env` 放在 Task 3.4**（与 SAVEPOINT 同批）。

- [x] 2.1 新增 `tests/support/utils.py`：`bootstrap_test_env()`（可选，§1 完成后简化 conftest import 前逻辑）
- [x] 2.2 文档化：`cache_clear` 仅允许 `env.py`（design 纪律）

## 3. SAVEPOINT + integration_client（POC 门禁）

- [x] 3.0 **POC**：`db_session` + SAVEPOINT + `get_db` override + `integration_client`；用例「注册→开店→rollback 后 users/shops 无残留」；验证 `login_admin` 可读 migration seed
- [x] 3.1 `conftest`：`db_session` 注册 override（不 close session）、`integration_client` 依赖 `db_session`；保留 plain `client`
- [x] 3.2 确认 override 生命周期：`reset_engine` 仅清 app 全局 engine，不 dispose 测试 fixture engine；autouse **保留**
- [x] 3.3 删除 `app/ordering/service.py` 中 `_get_reservation_ttl()` 的 `os.environ` 分支
- [x] 3.4 删除 helpers 内全部 `ensure_integration_auth_env`（~14 处）、`conftest` autouse、`tests/infra/test_auth.py`；删除冗余 `configure_integration_test_env` 常量
- [x] 3.5 grep inventory：`db_session` / `client` / `database_url` / `seed_inactive_user` / `ensure_integration_auth_env` 用法清单

> **Apply 约定**：Task 3.0 POC 通过前不得开始 §5。

## 4. tests/support/db + 懒释放 backdate + seed

- [x] 4.1 新增 `tests/support/db/ordering.py`（`backdate_order_expires_at`、`get_order_status` 等）
- [x] 4.2 新增 `tests/support/db/catalog.py`（`get_product_stock` 等）
- [x] 4.3 迁移 ordering lazy-expire 用例：backdate + DB assert；**删除** `override_order_reservation_ttl` 与 **`wait_past_order_expiry`**
- [x] 4.4 `seed_inactive_user(session: AsyncSession, ...)`；删独立 `create_async_engine`
- [x] 4.4a 迁移 `tests/user/test_login.py`：`integration_client` + `db_session` 作用域内 seed
- [x] 4.4b 迁移 `tests/ordering/test_create_order_by_seller.py` 中 seed 调用
- [x] 4.5 design/spec 文档化探针例外：`test_admin_seed.py`、`test_readiness.py`、`test_user_summary.py` 不迁移 override

## 5. 单批测试大迁移（integration_client + Pipeline 删除 + helper 分域）

> 约 23–28 个文件；**每个 test 文件本节只 touch 一次**。POC 通过后可在 dedicated 分支集中完成。

- [x] 5.1 全量 `@integration` HTTP 用例：`client` → `integration_client`（health / 探针例外除外）
- [x] 5.2 瘦身 `*Context`（`access_token`）；`bearer_headers(token: str)`；Setup fixture 依赖 `integration_client`
- [x] 5.3 删除 `PipelineResult` / `pipeline.py`；替换全库 `.root.step(...)` 引用
- [x] 5.4 拆分 `helpers.py` → `auth.py`、`catalog.py`、`ordering.py`；更新 conftest re-export
- [x] 5.5 更新 `.cursor/rules/test-architecture.mdc`、`docs/decision/测试与数据库策略.md`（SAVEPOINT + 探针例外）
- [x] 5.6 grep 验收：无 `PipelineResult`、无 `override_order_reservation_ttl`、无 `wait_past_order_expiry`、test 无 `from app.*.repository`

## 6. tests/support/db/ 强化：Seed + Assert 全覆盖

> design D5 扩展：``db/`` 接管 Arrange 阶段的域数据铺设（seed）和 Assert 阶段的副作用验证。
> 目标：Arrange 不经 HTTP，Assert 不走 HTTP GET。HTTP 只负责 Act 那一跳。
>
> 边界：conftest fixture（``authenticated_user``、``shop_owner``、``admin_auth_headers``）
> 保持 HTTP — JWT token 生成依赖 auth service 逻辑，不应在 DB 侧重复。

### 6a. 新增 seed helpers

> 每个 seed 函数接收 ``AsyncSession``（同一 SAVEPOINT 事务），
> 用 ORM model INSERT + ``flush()``，返回主键 ID。不经 HTTP stack。

- [x] 6a.1 `tests/support/db/catalog.py`：追加
  ``seed_shop(session, *, owner_user_id, name, status="active") → shop_id``、
  ``seed_category(session, *, name, parent_id=None) → category_id``、
  ``seed_product(session, *, shop_id, name, price, stock, is_published=False) → product_id``、
  ``seed_product_category(session, *, product_id, category_id, is_primary=False) → None``
- [x] 6a.2 `tests/support/db/ordering.py`：追加
  ``seed_order(session, *, buyer_user_id, shop_id, total_amount, expires_at=None, status="awaiting_payment", initiated_by="buyer") → order_id``、
  ``seed_order_item(session, *, order_id, product_id, product_name, unit_price, qty) → item_id``

### 6b. Assert 替换：HTTP GET → db/ 断言

> 当前部分测试 Act 是写操作（下单/取消/支付），却通过 HTTP GET ``/products/{id}``
> 验证库存变化。这违反 design D5「DB 断言替代 HTTP GET 作为状态验证路径」。

- [x] 6b.1 `tests/ordering/test_cancel_order.py`：3 个测试 — 删除 4 处 ``GET /products/{id}``，改用 ``get_product_stock``
- [x] 6b.2 `tests/ordering/test_create_order.py`：3 个测试 — 删除 5 处 ``GET /products/{id}``，改用 ``get_product_stock``
- [x] 6b.3 `tests/ordering/test_create_order_by_seller.py`：1 个测试 — 删除 1 处 ``GET /products/{id}``
- [x] 6b.4 `tests/ordering/test_pay_order.py`：2 个测试 — 删除 2 处 ``GET /products/{id}``
- [x] 6b.5 lazy-expire 测试（`test_list_orders.py` / `test_pay_order.py`）：清理残留的 HTTP GET ``/products/{id}``（旁已有 ``get_product_stock`` 断言）

### 6c. Arrange 迁移：HTTP → db/ seed

> 将 ``arrange_purchasable_product`` / ``arrange_confirmed_order`` 等 orchestrator
> 的 HTTP Arrange 替换为 ``db/`` seed，减少测试 Arrange 阶段的 HTTP 往返次数。
> conftest identity fixture 保持 HTTP（JWT token 生成不重复）。

- [x] 6c.0 更新 `tests/support/helper/ordering.py` 的
  ``arrange_purchasable_product``、``arrange_confirmed_order`` →
  调用 ``db/`` seed 替代 HTTP helper（``create_category``/``create_product``）。
  返回类型从 ``(CategoryResult, ProductResult)`` 变为 ``(category_id, product_id)``。
- [x] 6c.1 `tests/ordering/test_create_order.py`：``arrange_purchasable_product`` → ``db/`` seed
- [x] 6c.2 `tests/ordering/test_cancel_order.py`：``arrange_confirmed_order`` / ``arrange_purchasable_product`` → ``db/`` seed
- [x] 6c.3 `tests/ordering/test_pay_order.py`：同模式迁移
- [x] 6c.4 `tests/ordering/test_shipments_and_receipt.py`：同模式迁移
- [x] 6c.5 `tests/ordering/test_list_orders.py`：同模式迁移
- [x] 6c.6 `tests/ordering/test_create_order_by_seller.py`：同模式迁移
- [x] 6c.7 catalog 域测试（`test_public_products.py`、`test_update_product.py` 等）：``create_category`` + ``create_product``（HTTP）→ ``seed_category`` + ``seed_product``
- [x] 6c.8 CI 全绿（111 passed，17.21s）

## 7. CI 与收尾

- [ ] 7.1 `devbox run -- task ci` 全绿
- [ ] 7.2 archive 前 sync delta spec 至 `openspec/specs/test-architecture/spec.md`
