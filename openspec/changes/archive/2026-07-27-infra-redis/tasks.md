## 1. devbox 与 Taskfile（Redis 8 本地提供）

> 本 Task 仅交付 devbox Redis 与启动脚本；**不**修改业务域；**不**将 `redis:up` 挂入 `task dev`。

- [x] 1.1 `devbox.json` / `devbox.lock` 增加 `redis@8.0.x`（pin patch）；`.gitignore` 补充 `redis-data/`（若使用项目内数据目录）
- [x] 1.2 新增 `scripts/devbox_redis_up.sh`、`scripts/devbox_redis_down.sh`（启动 → `redis-cli ping` 轮询 → 摘要；down 停 devbox service）
- [x] 1.3 `Taskfile.yml` 增加 `redis:up`、`redis:down`；**不**修改 `dev` 的 `deps`
- [x] 1.4 手动验证：`devbox run -- task redis:up` 返回 PONG；`devbox run -- task redis:down` 可停止

## 2. 配置、Redis 客户端与 readiness（TDD）

> 按 `specs/infra-redis/spec.md` 与 `specs/infra-readiness/spec.md`：**先写失败测试，再实现**。

- [x] 2.1 `pyproject.toml` 增加 `redis`（redis-py）；更新 `integration` marker 描述（MySQL + Redis、`task db:up` + `task redis:up`）；`.env.example` 增加 `REDIS_URL`（dev `/0`、注释 test 用 `/1`）；`.env.test` 增加 `REDIS_URL=redis://127.0.0.1:6379/1`
- [x] 2.2 `tests/conftest.py` 增加 `redis_url`（session）与 `redis_client`（async，经 `get_redis()`）fixture；Redis 写 key 的用例使用 `flush_test_redis_db` fixture（对当前逻辑库 `FLUSHDB`，**禁止** `FLUSHALL`）
- [x] 2.3 编写 `tests/infra/test_redis.py`（Settings 必填、`redis_client` PING、SET/GET/TTL）；**扩展**已有 `tests/ops/test_readiness.py`（mysql+redis 均 ok / redis unavailable / 双 unavailable）；**不编写**实现
- [x] 2.4 `devbox run -- task db:up` + `devbox run -- task redis:up` 后跑 §2.3 测试，确认失败（红）；在 commit 或本文件记录预期失败原因
- [x] 2.5 `app/infra/config.py` 增加必填 `redis_url`；新增 `app/infra/redis.py`（`redis.asyncio` 连接池 + `get_redis` + `reset_redis`）
- [x] 2.6 扩展 `app/infra/readiness/service.py` 与 `router.py`：`checks.redis`；双依赖 ok 才 `ready`
- [x] 2.7 `devbox run -- task db:up` + `devbox run -- task redis:up` 后跑 §2 测试，确认通过（绿）；`conftest` 对 integration 用例 autouse `reset_redis`（镜像 `reset_engine`）

## 3. 本地验证与远程 CI

- [x] 3.1 `.github/workflows/ci.yml` 增加 `services.redis`（`redis:8.0` + healthcheck）与 `REDIS_URL` env（`/1`）
- [x] 3.2 本地`devbox run -- task db:up`、`devbox run -- task redis:up`、`devbox run -- task migrate`、`devbox run -- task ci` 全绿
- [x] 3.3 push 并确认 GitHub Actions CI 全绿（workflow_dispatch [run #30234717824](https://github.com/EudaimoniAya/e-commerce-system/actions/runs/30234717824) success）

## 4. 归档

- [x] 4.1 更新 `docs/decision/测试与数据库策略.md`：增补 Redis 小节（本地 devbox / CI container / 8.0 / db 0 vs 1）
- [x] 4.2 更新 `docs/architecture.md`：`infra/redis.py`、`REDIS_URL`、readiness 含 redis
- [x] 4.3 `/opsx:archive` 并 sync specs（`infra-redis` 新增、`infra-readiness` delta）
