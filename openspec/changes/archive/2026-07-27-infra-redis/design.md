## Context

`infra-database`、`infra-readiness`、`infra-logging-and-errors` 及 user/catalog/ordering 业务域已交付。当前 `Settings` 仅含 `DATABASE_URL` 等字段；readiness 仅 ping MySQL；devbox 提供 `mysql80`，CI 使用 `services.mysql`（`mysql:8.0`）。架构与 ADR-002 约定：本地 devbox、CI service container、同一套 integration 测试；**不**采用本地 docker-compose。

后续 change（手机验证码、JWT 黑名单、订单 TTL）将消费 Redis，但 **本 change 不实现任何业务用法**。

约束：

- infra **不得** import 任何业务域模块；业务域将来 **仅** 通过 `app/infra/redis.py` 获取客户端
- 数据库/Redis/测试命令须 `devbox run --` 包装
- integration 测试使用 `AsyncClient`；Redis integration 须连接 **真实 devbox/CI 实例**（与 MySQL 一致）

## Goals / Non-Goals

**Goals:**

- 本地 devbox 单实例 Redis 8.0.x + `task redis:up` / `redis:down` + 就绪轮询
- CI `services.redis`（`redis:8.0`）+ `REDIS_URL` 环境变量
- 必填 `REDIS_URL`；dev 使用逻辑库 **db 0**，test/CI 使用 **db 1**
- `app/infra/redis.py`：`redis.asyncio` 连接池与 `get_redis()` FastAPI 依赖
- readiness 聚合 **mysql + redis**；二者均 ok 才 `ready`
- 最小 integration 测试（连通 + 基本命令）；更新 ADR / architecture / `.env.example`

**Non-Goals:**

- Redis 主从、哨兵、Cluster；Layer B HA / failover 测试
- 业务 key、验证码、黑名单、购物车迁 Redis
- `task dev` 依赖 `redis:up`（首个业务 consumer change 再评估）
- 本地 docker-compose；Terraform/K8s；生产 AOF/RDB/密码策略（部署 change）
- RediSearch / RedisJSON 等 8.x 高级特性

## Decisions

### 1. 本地提供方式：devbox services（非 docker-compose）

**选择**：`devbox add redis@8.0.x`（pin patch，如 `8.0.3`），`devbox services up redis`，脚本 `scripts/devbox_redis_up.sh` / `_down.sh` 镜像 MySQL 脚本的「启动 → 轮询 → 摘要」模式。

**理由**：与 ADR-002 MySQL 策略一致；WSL 已验证 devbox 工具链；避免本地双轨（devbox + compose）。

**备选**：docker-compose Redis（ADR 已否决）；裸 apt install（不可复现）。

### 2. CI 提供方式：GitHub Actions service container

**选择**：

```yaml
services:
  redis:
    image: redis:8.0
    ports: ["6379:6379"]
    options: >-
      --health-cmd="redis-cli ping"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=5
env:
  REDIS_URL: redis://127.0.0.1:6379/1
```

**理由**：与 `services.mysql` 对称；每 job 干净实例；内置 healthcheck。

**备选**：runner 上 apt install redis-server（生命周期与版本难管）；CI 内 docker-compose（过重）。

### 3. Redis 大版本：8.0.x

**选择**：本地 `redis@8.0.x`；CI `redis:8.0` 镜像。

**理由**：与 `mysql80` 对称；devbox index 可 pin 8.0 patch；后续业务可用 8 内置能力。

**备选**：Redis 7.x（无必要降级）。

### 4. 配置：`REDIS_URL` 必填

**选择**：`Settings.redis_url: str`（无默认值）；缺失时 pydantic 校验失败。

**理由**：与 `database_url` 一致；避免静默连错实例；readiness 始终检查 Redis。

**备选**：可选 Redis + feature flag（YAGNI，增加 readiness 分支）。

### 5. dev / test 隔离：逻辑库编号

| 环境 | URL 示例 |
|------|----------|
| dev（`.env`） | `redis://127.0.0.1:6379/0` |
| test（`.env.test`、CI） | `redis://127.0.0.1:6379/1` |

**理由**：类比 MySQL `ecommerce_dev` / `ecommerce_test`；单进程、零额外端口。

**限制**：`FLUSHALL` 清全部 db；将来若上 Redis Cluster（仅 db 0）需改为 key 前缀——写入 ADR。

**备选**：双 Redis 实例不同端口（更重）。

### 6. 客户端：redis-py + redis.asyncio

**选择**：

- 依赖：`redis`（redis-py，≥5.x asyncio 支持）
- 模块级懒加载连接池 / `Redis` 实例（对齐 `get_engine()` 进程内单例思路）
- 暴露 `async def get_redis() -> Redis` 供 FastAPI `Depends`
- 应用 lifespan 或显式 `close` 释放连接

**理由**：与 FastAPI 异步栈一致；社区标准库。

**调试**：人工仍用 `redis-cli`（devbox PATH）；与 Python 客户端角色分离。

**禁止**：业务域 `from redis.asyncio import Redis` 自行 `from_url`（仅 infra 持有连接）。

**备选**：hiredis 加速（本 change 不引入）；fakeredis（仅适合纯单元测，integration 用真实例）。

### 7. 本地持久化：弱化 + gitignore

**选择**：dev 依赖 devbox Redis plugin 默认数据目录；若写入项目内目录则 `redis-data/` gitignore；不强制 AOF。

**理由**：本 change 无业务 key；验证码/TTL 类数据本就 ephemeral。

**生产**：部署 change 定 AOF/RDB/密码/托管 Redis。

### 8. readiness 语义

**选择**：

- `ready` ⇔ `mysql` ok **且** `redis` ok
- 任一 unavailable → `503`，`status: not_ready`
- `checks: { mysql: ok|unavailable, redis: ok|unavailable }`
- **不**提供 Redis 可选跳过开关

**理由**：`infra-readiness` 已设计统一 `checks` 结构；本 change 起 Redis 为硬依赖（Settings 必填）。

**实现**：readiness 路由为 **sync** `def`，与现有 MySQL 探针一致。`is_redis_ready()` 提供 **sync 入口**（镜像 `is_mysql_ready()`）：无 running loop 时 `asyncio.run(_ping_redis())`；pytest-asyncio 等已有 loop 场景在 `ThreadPoolExecutor` 中 `asyncio.run` 独立 ping，避免与全局 `Redis` 连接池跨事件循环冲突。底层 `_ping_redis()` 使用 **独立短连接**（`Redis.from_url` + `ping` + `aclose`），不借用 `get_redis()` 全局池。

### 9. Taskfile：`redis:up` / `redis:down`，不绑 `dev`

**选择**：独立 task；`task ci` **不**隐式启动 MySQL 或 Redis（与 ADR-002 一致：`task ci` 只跑 ruff + pytest，数据库与 Redis 由开发者本地预先 `task db:up` / `task redis:up`，或由 CI workflow 的 `services.mysql` / `services.redis` 提供）。

**理由**：当前业务不依赖 Redis；避免 `task dev` 强制多起服务；保持 CI Taskfile 与本地 CI 脚本职责单一。

### 10. 测试 fixture 与隔离策略

**选择**：

| 项 | 策略 |
|----|------|
| Redis 客户端测试位置 | `tests/infra/test_redis.py`（与 `test_database.py` 并列） |
| readiness 测试位置 | **扩展**已有 `tests/ops/test_readiness.py`（与 `test_health.py` 并列，不迁移） |
| `redis_url` fixture | session 级，从 `get_settings().redis_url` 读取（镜像 `database_url`） |
| `redis_client` fixture | async，经 `get_redis()` 注入，供 `test_redis.py` 使用 |
| 写 key 用例清理 | `flush_test_redis_db` fixture：对 **当前 URL 逻辑库** 执行 `FLUSHDB`（test 为 db 1）；禁止 `FLUSHALL` |
| 连接池跨 loop | integration 用例 autouse `reset_redis()`（镜像 `reset_engine`） |
| readiness 失败路径 | `unittest.mock.patch` `is_redis_ready` / `is_mysql_ready`（与现有 MySQL unavailable 测试一致） |

**理由**：探针测放 `tests/ops/`、infra 模块测放 `tests/infra/`，与 test-architecture 目录约定一致；fixture 显式化，apply 时不猜测 conftest 变更范围。

### 11. ADR 文档

**选择**：在 `docs/decision/测试与数据库策略.md` 增补 **Redis** 小节（或同级 ADR），表格镜像 MySQL（本地 devbox / CI container / 大版本 / db 0 vs 1）。

## Risks / Trade-offs

- **[Risk] devbox Redis plugin 端口/配置与脚本假设不一致** → 以 `devbox services` 环境变量（`REDIS_PORT` 等）为准；脚本用 `redis-cli -p "$REDIS_PORT" ping`
- **[Risk] readiness 增加 Redis 后，未起 Redis 时本地 `task dev` 仍可用但 `/health/ready` 503** → 可接受；liveness `/health` 不变；文档说明跑 Redis 测试前 `task redis:up`
- **[Risk] 测试污染 dev db** → 强制 test 使用 `/1`；写 key 用例用 `flush_test_redis_db`（`FLUSHDB` 当前库）；见 Decision 10
- **[Risk] CI runner 内存随 mysql+redis 增加** → 仅两 service，可接受；不堆 HA 拓扑

## Migration Plan

1. 合并本 change 后：开发者 `devbox run -- task redis:up`，`.env` / `.env.test` 补充 `REDIS_URL`
2. 无数据库式 migration；无业务数据迁移
3. 回滚：移除 Redis 依赖与 readiness 检查；revert devbox/CI 配置

## Open Questions

- （无）patch 版本在 apply 时以 `devbox add redis@8.0.3` 或当前 index 最新 8.0.x 为准，写入 `devbox.lock`
