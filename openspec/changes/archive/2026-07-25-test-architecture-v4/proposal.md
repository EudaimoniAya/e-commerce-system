## Why

第三次测试架构 refactor（`test-architecture`）引入了 `PipelineResult` 与纯 HTTP 断言，但 **HTTP 集成测实际走 app 全局 engine 并 commit**，而 `db_session` fixture 使用独立 engine 的 rollback **无法撤销 HTTP 数据**，导致 `ecommerce_test` 残留与 `unique_*` 防碰撞依赖。同时 Settings 在 conftest/helpers 中硬编码覆盖、TTL 测试污染生产 `ordering.service`，维护成本高。ordering 双路径交付完成后，适合做一次 **第四次测试架构 refactor**：统一 `.env.test`、`dependency_overrides` + SAVEPOINT 单事务隔离、DB 状态断言、删除 Pipeline。

## What Changes

- **测试环境**：新增 `.env.test`；`app/infra/config.py` 支持 `APP_ENV_FILE`（默认 `.env`）；`task test` / CI 注入 `APP_ENV_FILE=.env.test`；删除 helpers 内 duplicate JWT/DB 常量
- **Settings 缓存**：会话级稳定 env；删除 helper 内 `ensure_integration_auth_env()`（含 `tests/infra/test_auth.py`）；`cache_clear` 仅允许 `tests/support/env.py` 生命周期边界
- **事务隔离（核心）**：`db_session` fixture 注册 `get_db` dependency override + SAVEPOINT；新增 `integration_client`（依赖 `db_session`）；保留普通 `client` 供 health 等无 DB 写库测
- **DB 断言**：新增 `tests/support/db/`（封装只读 Repository）；HTTP Act + DB Assert；禁止为断言调用 service
- **懒释放测试**：删除生产 TTL env 后门；删除 `override_order_reservation_ttl` 与 **`wait_past_order_expiry`**；改用 **backdate** `orders.expires_at`
- **数据流（§5 单批大迁移，约 23–28 个测试文件各 touch 一次）**：`client` → `integration_client`；删除 `PipelineResult`；瘦身 `*Context`（`access_token`）；`bearer_headers(token: str)`；helper 按域拆分
- **seed**：`seed_inactive_user(session, ...)`；连锁迁移 `test_login.py`、`test_create_order_by_seller.py` 至 SAVEPOINT 作用域
- **探针例外**：`tests/catalog/test_admin_seed.py` 等 migration/ops 探针 **不**迁移 override 模式，design/spec 文档化
- **文档**：修订 ADR-002、`.cursor/rules/test-architecture.mdc`

## Non-goals

- 不引入 Testcontainer、Truncate 清表、pytest-xdist 并行 integration
- 不实现 conftest `APP_ENV_FILE` setdefault 兜底（暂不做；约定 `devbox run -- task test`）
- 不修改业务 API 契约或新增 migration
- 不删除 `unique_*` builders（单测内多实体仍需要）
- 不做测间 email/shop name 复用优化
- 不新增 formal「Service 集成子模式」marker（仅 fixture 配方：HTTP 用 `integration_client`，纯 service 用 `db_session`）

## Capabilities

### New Capabilities

（无新增全局 capability；本 change 为测试基础设施演进。）

### Modified Capabilities

- `test-architecture`：SAVEPOINT + integration_client/db_session override、tests/support/db、DB Assert、Settings/env 规范、删除 Pipeline（根因：DB 可查 + fixture 依赖链，非认知成本）、探针例外、POC 门禁、§5 单批测试文件迁移

## Impact

- **业务域（生产）**：`app/infra/config.py`（`APP_ENV_FILE`）；`app/ordering/service.py`（删除 TTL env 后门）
- **测试**：`tests/conftest.py`、`tests/support/**`、约 23–28 个 integration 测试文件（§5 单批）、ordering 懒释放、seed 调用方、`.env.test`、Taskfile/CI
- **文档与规范**：`openspec/specs/test-architecture/`、`docs/decision/测试与数据库策略.md`、`.cursor/rules/test-architecture.mdc`
- **API / 依赖**：无运行时 API 变更
