## 1. devbox 与 Taskfile（Redis 8 本地提供）

> 本 Task 仅交付 devbox Redis 与启动脚本；**不**修改业务域；**不**将 `redis:up` 挂入 `task dev`。

- [ ] 1.1 `devbox.json` / `devbox.lock` 增加 `redis@8.0.x`（pin patch）；`.gitignore` 补充 `redis-data/`（若使用项目内数据目录）
- [ ] 1.2 新增 `scripts/devbox_redis_up.sh`、`scripts/devbox_redis_down.sh`（启动 → `redis-cli ping` 轮询 → 摘要；down 停 devbox service）
- [ ] 1.3 `Taskfile.yml` 增加 `redis:up`、`redis:down`；**不**修改 `dev` 的 `deps`
- [ ] 1.4 手动验证：`devbox run -- task redis:up` 返回 PONG；`devbox run -- task redis:down` 可停止

## 2. 配置、Redis 客户端与 readiness（TDD）

> 按 `specs/infra-redis/spec.md` 与 `specs/infra-readiness/spec.md`：**先写失败测试，再实现**。

- [ ] 2.1 `pyproject.toml` 增加 `redis`（redis-py）；更新 `integration` marker 描述（MySQL + Redis、`task db:up` + `task redis:up`）；`.env.example` 增加 `REDIS_URL`（dev `/0`、注释 test 用 `/1`）；`.env.test` 增加 `REDIS_URL=redis://127.0.0.1:6379/1`
- [ ] 2.2 `tests/conftest.py` 增加 `redis_url`（session）与 `redis_client`（async，经 `get_redis()`）fixture；Redis 写 key 的用例使用 `flush_test_redis_db` fixture（对当前逻辑库 `FLUSHDB`，**禁止** `FLUSHALL`）
- [ ] 2.3 编写 `tests/infra/test_redis.py`（Settings 必填、`redis_client` PING、SET/GET/TTL）；**扩展**已有 `tests/ops/test_readiness.py`（mysql+redis 均 ok / redis unavailable / 双 unavailable）；**不编写**实现
- [ ] 2.4 `devbox run -- task db:up` + `devbox run -- task redis:up` 后跑 §2.3 测试，确认失败（红）；在 commit 或本文件记录预期失败原因
- [ ] 2.5 `app/infra/config.py` 增加必填 `redis_url`；新增 `app/infra/redis.py`（`redis.asyncio` 连接池 + `get_redis` + `reset_redis`）
- [ ] 2.6 扩展 `app/infra/readiness/service.py` 与 `router.py`：`checks.redis`；双依赖 ok 才 `ready`
- [ ] 2.7 `devbox run -- task db:up` + `devbox run -- task redis:up` 后跑 §2 测试，确认通过（绿）；`conftest` 对 integration 用例 autouse `reset_redis`（镜像 `reset_engine`）

## 3. CI Redis service container

- [ ] 3.1 `.github/workflows/ci.yml` 增加 `services.redis`（`redis:8.0` + healthcheck）与 `REDIS_URL` env（`/1`）
- [ ] 3.2 本地 `devbox run -- task ci` 全绿（含 Redis integration）

## 4. 文档

- [ ] 4.1 更新 `docs/decision/测试与数据库策略.md`：增补 Redis 小节（本地 devbox / CI container / 8.0 / db 0 vs 1）
- [ ] 4.2 更新 `docs/architecture.md`：`infra/redis.py`、`REDIS_URL`、readiness 含 redis

## 5. 本地验证与远程 CI

- [ ] 5.1 `devbox run -- task db:up`、`devbox run -- task redis:up`、`devbox run -- task migrate`、`devbox run -- task ci` 全绿
- [ ] 5.2 push 并确认 GitHub Actions CI 全绿（或 `workflow_dispatch`）；更新本 tasks 勾选

## 6. 归档

- [ ] 6.1 `/opsx:archive` 并 sync specs（`infra-redis` 新增、`infra-readiness` delta）
