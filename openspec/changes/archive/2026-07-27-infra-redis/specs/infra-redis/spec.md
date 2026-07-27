## ADDED Requirements

### Requirement: Redis URL configuration

系统 SHALL 通过 `pydantic-settings` 从环境变量加载必填配置 `REDIS_URL`（Redis 连接 URI，含 host、port 与逻辑库编号）。配置不得硬编码于业务代码。

#### Scenario: 缺少 REDIS_URL 时应用启动失败

- **WHEN** 未设置 `REDIS_URL` 且应用工厂或 Settings 初始化需要 Redis 配置
- **THEN** 系统 SHALL 以明确校验错误失败，而非静默使用默认 localhost

#### Scenario: REDIS_URL 指向有效 Redis 实例

- **WHEN** `REDIS_URL` 设置为可连接的 Redis URI（如 `redis://127.0.0.1:6379/0`）
- **THEN** infra Redis 客户端 SHALL 使用该 URL 建立连接

### Requirement: Dev and test logical database separation

系统 SHALL 约定：本地开发默认使用 Redis 逻辑库 **db 0**；pytest integration 与 CI SHALL 使用逻辑库 **db 1**，以避免测试 key 污染开发环境。

#### Scenario: 测试环境使用 db 1

- **WHEN** pytest integration 测试或 CI job 运行且加载 `.env.test` 或等价 `REDIS_URL`
- **THEN** `REDIS_URL` 的路径部分 SHALL 指定逻辑库编号 `1`（即 URI 以 `/1` 结尾或等价）

#### Scenario: 开发环境使用 db 0

- **WHEN** 本地开发加载默认 `.env` 示例配置
- **THEN** 文档或 `.env.example` SHALL 示例 `REDIS_URL` 使用逻辑库编号 `0`

### Requirement: Async Redis client in infra

系统 SHALL 在 `app/infra/` 提供基于 **redis-py** `redis.asyncio` 的共享 Redis 客户端（连接池或等价复用）及 FastAPI 可注入依赖（如 `get_redis`）。业务域与测试 SHALL 通过 infra 暴露的 `get_redis`（或等价依赖）访问 Redis，**仅 infra 模块** 持有 `Redis.from_url` 与连接池生命周期。

#### Scenario: 依赖注入返回可用 Redis 客户端

- **WHEN** integration 测试通过 `get_redis` 获取客户端并执行 `PING`
- **THEN** 命令 SHALL 返回 `True` 或等价成功且连接可被正确关闭或归还池

#### Scenario: 基本读写与 TTL

- **WHEN** integration 测试对测试 key 执行 `SET` 带 `ex`、随后 `GET`
- **THEN** SHALL 读回写入的值且在 TTL 到期后 key 不可读（或已过期）

### Requirement: Local Redis via devbox

系统 SHALL 通过 devbox 提供本地 Redis **8.0.x** 单实例；SHALL 提供 `task redis:up` 与 `task redis:down`（或等价 Taskfile 任务）及就绪轮询（`redis-cli ping` 返回 `PONG`），镜像 MySQL `task db:up` 纪律。

#### Scenario: redis up 后就绪

- **WHEN** 开发者在项目根目录执行 `devbox run -- task redis:up` 且 Redis 正常启动
- **THEN** 脚本 SHALL 在超时内检测到 `PONG` 并输出就绪摘要（含连接地址或端口提示）

#### Scenario: redis down 停止服务

- **WHEN** 开发者执行 `devbox run -- task redis:down`
- **THEN** devbox Redis 服务 SHALL 停止且不遗留需手动杀死的 redis-server 进程（在 devbox 托管范围内）

### Requirement: CI Redis service container

GitHub Actions CI workflow SHALL 声明 `services.redis` 使用 **`redis:8.0`** 镜像，配置 healthcheck（`redis-cli ping`）与端口 `6379`；job 环境 SHALL 设置 `REDIS_URL` 指向 `127.0.0.1:6379/1`。

#### Scenario: CI job 启动 Redis sidecar

- **WHEN** CI workflow 运行 `ci` job
- **THEN** Redis service container SHALL 在 pytest 步骤前通过 healthcheck 就绪

#### Scenario: CI 与本地共用同一套 Redis integration 测试

- **WHEN** 同一 Redis integration 测试在本地（devbox Redis + `.env.test`）与 CI 中执行
- **THEN** 二者 SHALL 均通过，且使用相同 Redis 大版本 8.0 系列

### Requirement: Redis integration tests

系统 SHALL 提供 `@pytest.mark.integration` 标识的 Redis 相关测试（数量精简，建议不超过 3 个模块级用例），验证配置加载、PING 与基本 SET/GET/TTL；readiness 中 redis 检查 SHALL 在 `tests/ops/test_readiness.py` 扩展。上述 integration 路径 SHALL 连接真实 Redis 实例（devbox 或 CI service container）。

#### Scenario: integration marker 存在

- **WHEN** 查看 `tests/infra/test_redis.py` 与扩展后的 `tests/ops/test_readiness.py` 中 Redis 相关用例
- **THEN** 这些测试 SHALL 带有 `integration` marker

#### Scenario: conftest 提供 Redis 测试 fixture

- **WHEN** `tests/infra/test_redis.py` 需要 Redis 客户端
- **THEN** `tests/conftest.py` SHALL 提供 `redis_url` 与 `redis_client` fixture，且写 key 用例 SHALL 可通过 `flush_test_redis_db` 清理当前逻辑库（`FLUSHDB`）
