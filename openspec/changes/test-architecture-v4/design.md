## Context

第三次测试架构 refactor（`test-architecture`）建立了四层分工与 `PipelineResult`。`PipelineResult` 当初的价值是 **类型安全的步骤链**（`root.step(ShopResult)` + IDE 推断），认知成本可控。真正过时的是：HTTP 与 `db_session` **双 engine**，以及为传递持久 ID 而依赖 Pipeline——SAVEPOINT 后 **DB 可查状态**，fixture 依赖链 + `access_token` 即可。

Settings 在 helpers 硬编码覆盖；ordering 懒释放测污染生产 `_get_reservation_ttl()`。

## Goals / Non-Goals

**Goals:**

- 统一测试环境：`.env.test` + `APP_ENV_FILE` + `task test`/CI 注入
- HTTP 集成测 **单事务零残留**：`dependency_overrides(get_db)` + SAVEPOINT + 外层 rollback
- 区分 `client`（无 override）与 `integration_client`（依赖 `db_session`）
- DB 状态断言经 `tests/support/db/`
- 懒释放：**backdate**；删除 TTL/wait 辅助函数
- **§5 单批**：同一测试文件一次性完成 `integration_client` + 瘦身 Context + 删 Pipeline + helper 分域
- SAVEPOINT POC 通过后再 §5

**Non-Goals:**

- Testcontainer、Truncate、pytest-xdist 并行 integration
- conftest `APP_ENV_FILE` setdefault 兜底
- 删除 `unique_*`
- 迁移 `test_admin_seed.py` 至 override 模式（见 D10 例外）

## Decisions

### D1: `.env.test` + `APP_ENV_FILE`（复用生产 Settings）

见 proposal。拒绝 conftest duplicate loading。

### D2: Settings 缓存生命周期

- 会话 env 稳定 → 默认零次 `cache_clear`
- `cache_clear` 仅 `tests/support/env.py` + 极少数 mutating fixture teardown
- **禁止** helper 内 `ensure_integration_auth_env()`（helpers 约 14 处 + `conftest` autouse + `tests/infra/test_auth.py`）
- **删 ensure** 与 §3 SAVEPOINT **同批**（Task 3.4），删后全量 CI 盯 401

### D3: `integration_client` vs `client`（选项 B）

| Fixture | 依赖 | `get_db` | 用途 |
|---------|------|----------|------|
| `client` | 无 | 生产路径 | health 等 |
| `integration_client` | `db_session` | override | `@integration` HTTP 业务测 |

### D4: override 挂在 `db_session` fixture

```text
await reset_engine()                    # 仅 dispose app 模块级 _engine
  db_session:
    测试 create_async_engine → outer BEGIN → SAVEPOINT session
    dependency_overrides[get_db] → yield 同一 session（不 close）
    yield session
    pop override → outer ROLLBACK
await reset_engine()
```

**与 `reset_engine` 的关系（已收敛，非 Open Question）：**

- `reset_engine()` **只**清理 `app.infra.database` 全局 `_engine`，**不** dispose `db_session` fixture 的测试 engine
- integration autouse **`保留`** 两次 `reset_engine`，防止无 override 路径误建全局连接池
- override active 期间 HTTP 走测试 session，与全局 engine dispose **无冲突**

### D5: DB 断言 — `tests/support/db/`

只读 Repository + 同一 `db_session`。禁止 Case import `app.*.repository`；禁止为 Assert 调 service。

### D6: 懒释放 — backdate；删除 wait

删除 `override_order_reservation_ttl`、**`wait_past_order_expiry`**（与 TTL 同删，不留 fallback）、生产 `os.environ` TTL 分支。

### D7: 删除 Pipeline — 根因是 DB 可查 + fixture 链，非认知成本

- **删除** `PipelineResult`：持久 ID/状态改 `tests/support/db` 或 Act `*Result`；Setup 鉴权改瘦身 Context + **fixture 依赖链**
- **保留** v3 的 `*Result`（单次 HTTP）、fail-fast fixture、禁止 helper 收/返 Context
- `bearer_headers(access_token: str)`；helper 分域
- **禁止** proliferate 公开 `XxxSetup` dataclass

### D8: `seed_inactive_user` 迁入 `db_session`（含连锁）

签名 `(session: AsyncSession, email, password) -> str`。**必须**同步迁移调用方：

- `tests/user/test_login.py`（当前 `database_url` + 普通 `client`）
- `tests/ordering/test_create_order_by_seller.py`

二者须在 SAVEPOINT / `integration_client` 作用域内。

### D9: §5 单批大迁移（合并原 §4.5 + §5）

约 **23–28 个**测试文件。分批 touch 同一文件两次（先换 client、再删 Pipeline）回归成本高。**POC 通过后**在同一节（或 `refactor/test-architecture-v4` 分支）一次性完成：

- `client` → `integration_client`
- 瘦身 Context + `bearer_headers(token)`
- 删 Pipeline / `.root.step`
- helper 分域

### D10: 探针例外 — 不迁移 override 模式

下列测试 **不**使用 `integration_client` / SAVEPOINT override，design/spec **文档化例外**：

| 文件 | 原因 |
|------|------|
| `tests/catalog/test_admin_seed.py` | 子进程 `alembic upgrade head` + 独立 engine 查 seed |
| `tests/ops/test_readiness.py` | readiness 自建 engine ping（已有） |
| `tests/user/test_user_summary.py` | 纯 service + rollback `db_session`，无 HTTP |

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| SAVEPOINT + 多次 `commit()` 未验证 | Task 3.0 POC |
| migration seed 在事务内不可读 | POC 验证 `login_admin` |
| 删 ensure 后 401 回归 | Task 3.4 后全量 CI；含 `test_auth.py` |
| §5 改动面大 | 单批 + 每文件只改一次；POC 门禁 |
| integration 禁止 xdist | spec 写明 |

## Migration Plan

| 节 | 内容 |
|----|------|
| **§1** | `APP_ENV_FILE`、`.env.test`、Taskfile/CI |
| **§2** | `tests/support/env.py`；cache 纪律文档 |
| **§3** | SAVEPOINT + override + `integration_client`；POC；删 TTL 后门 + ensure |
| **§4** | `tests/support/db`；lazy-expire backdate；`seed_inactive_user` + 调用方 |
| **§5** | **单批**：integration_client + Context + Pipeline 删除 + helper 分域 + rules/ADR |
| **§6** | CI 全绿；sync spec |

**POC 门禁**：Task 3.0 通过前不得开始 §5。

**Inventory（Task 3.5）**：grep `db_session` / `client` / `database_url` / `seed_inactive_user` / `ensure_integration_auth_env`。

## Open Questions

- `join_transaction_mode="create_savepoint"` vs 每请求 `begin_nested()`（POC 选定）
