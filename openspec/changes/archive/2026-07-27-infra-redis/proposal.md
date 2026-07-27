## Why

业务域即将使用 Redis（短信验证码、JWT 黑名单、订单 TTL 等），但 infra 层尚无 Redis 连接、配置与就绪探针；本地与 CI 也缺少与 MySQL 对齐的 Redis 提供方式。架构文档与 ADR-002 已确立「本地 devbox、CI service container、同一套 integration 测试」惯例。现需在继续 user/ordering 等 Redis 消费 change 之前，先交付 **单实例 Redis 基础设施**。

## What Changes

- 在 **devbox** 引入 **Redis 8.0.x**（`redis@8.0.x`），提供 `task redis:up` / `task redis:down` 及就绪轮询脚本（镜像 `devbox_mysql_up.sh` 模式）
- 在 **`Settings`** 新增必填 **`REDIS_URL`**；本地 dev 使用逻辑库 **db 0**，测试/CI 使用 **db 1**
- 新增 **`app/infra/redis.py`**：`redis-py` **`redis.asyncio`** 连接池单例与 `get_redis()` 依赖；业务域 **禁止** 自行 `Redis.from_url`
- 扩展 **`GET /health/ready`**：`checks` 增加 **`redis`**，与 `mysql` 并列；二者均 ok 时 `status=ready`，否则 503
- 在 **CI**（`.github/workflows/ci.yml`）增加 **`services.redis`**（`redis:8.0` + healthcheck）与 `REDIS_URL` 环境变量
- 新增 **integration 测试**（PING / 基本 SET+GET+TTL 或 readiness 含 redis）；本地与 CI 同一套用例
- 更新 **`.env.example`**、**`docs/decision/测试与数据库策略.md`**（或等价 ADR 增补 Redis 一节）、**`docs/architecture.md`**（infra 模块说明）
- 在 **`pyproject.toml`** 增加 **`redis`** 依赖（redis-py）

## Non-goals

- **不** 引入 Redis 主从、哨兵、Cluster 或 Layer B HA 测试
- **不** 在本 change 实现任何业务 Redis 用法（验证码、购物车、黑名单、订单过期等）
- **不** 本地 docker-compose 提供 Redis（与 MySQL ADR 一致，本地用 devbox services）
- **不** 将 `redis:up` 挂入 **`task dev`** 的 `deps`（待首个业务 consumer change 再评估）
- **不** 引入 Terraform、K8s、生产持久化/AOF 策略（留给部署 change）
- **不** 使用 RediSearch / RedisJSON 等 8.x 高级特性（本 change 仅连通与 readiness）
- **不** 修改 user / catalog / ordering 业务 API 或行为

## Capabilities

### New Capabilities

- `infra-redis`: Redis 8 单实例配置、`REDIS_URL`、async 客户端、devbox/CI 提供方式、dev/test 逻辑库隔离约定

### Modified Capabilities

- `infra-readiness`: 聚合 readiness 在 MySQL 之外 **SHALL** 检查 Redis；`checks` 含 `redis` 键；双依赖均可用时返回 ready

## Impact

- **业务域**: 仅 **infra**（config、redis 模块、readiness）；无业务域代码变更
- **新增/修改文件**: `devbox.json`、`devbox.lock`、`scripts/devbox_redis_*.sh`、`Taskfile.yml`、`app/infra/config.py`、`app/infra/redis.py`、`app/infra/readiness/`、`.github/workflows/ci.yml`、`.env.example`、`tests/infra/`、`pyproject.toml`、`docs/`
- **API**: `GET /health/ready` 响应 `checks` 增加 `redis`（成功/失败形态见 spec delta）；无业务 REST 变更
- **依赖**: `redis`（redis-py，含 asyncio 支持）
- **环境**: 跑 Redis integration 测试或 readiness 验证前须 `devbox run -- task redis:up`；CI 由 workflow `services.redis` 提供
