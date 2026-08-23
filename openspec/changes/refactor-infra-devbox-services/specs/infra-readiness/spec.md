## MODIFIED Requirements

### Requirement: Aggregated readiness endpoint

系统 SHALL 提供无需认证的聚合 readiness 端点 `GET /health/ready`，用于检查应用是否可接收依赖 **MySQL、Redis 与 PostgreSQL（AI 读库）** 的业务流量。该端点 SHALL 与 liveness 端点 `GET /health` 分离；liveness SHALL 不依赖数据库或 Redis 或 PostgreSQL。任一检查为 `unavailable` 即 `not_ready`；SHALL NOT 要求单独覆盖「多库同时不可用」组合。

#### Scenario: MySQL、Redis 与 PostgreSQL 均可用时返回 ready

- **WHEN** MySQL、Redis 与 PostgreSQL 连接均正常且客户端请求 `GET /health/ready`
- **THEN** 响应状态码 SHALL 为 200
- **AND** 响应体 JSON SHALL 为 `{"status": "ready", "checks": {"mysql": "ok", "redis": "ok", "postgresql": "ok"}}`

#### Scenario: MySQL 不可用时返回 not_ready

- **WHEN** MySQL 不可连接且 Redis 与 PostgreSQL 可用，客户端请求 `GET /health/ready`
- **THEN** 响应状态码 SHALL 为 503
- **AND** 响应体 JSON SHALL 为 `{"status": "not_ready", "checks": {"mysql": "unavailable", "redis": "ok", "postgresql": "ok"}}`

#### Scenario: Redis 不可用时返回 not_ready

- **WHEN** Redis 不可连接且 MySQL 与 PostgreSQL 可用，客户端请求 `GET /health/ready`
- **THEN** 响应状态码 SHALL 为 503
- **AND** 响应体 JSON SHALL 为 `{"status": "not_ready", "checks": {"mysql": "ok", "redis": "unavailable", "postgresql": "ok"}}`

#### Scenario: PostgreSQL 不可用时返回 not_ready

- **WHEN** PostgreSQL 不可连接且 MySQL 与 Redis 可用，客户端请求 `GET /health/ready`
- **THEN** 响应状态码 SHALL 为 503
- **AND** 响应体 JSON SHALL 为 `{"status": "not_ready", "checks": {"mysql": "ok", "redis": "ok", "postgresql": "unavailable"}}`

#### Scenario: 响应 Content-Type 为 JSON

- **WHEN** 客户端请求 `GET /health/ready`
- **THEN** 响应 `Content-Type` SHALL 包含 `application/json`
