## ADDED Requirements

### Requirement: Health liveness endpoint

系统 SHALL 提供无需认证的存活探针端点 `GET /health`，用于冒烟测试及后续部署 liveness 探针。该端点不依赖数据库或外部服务。

#### Scenario: 服务正常时返回 200

- **WHEN** 客户端请求 `GET /health`
- **THEN** 响应状态码为 200
- **AND** 响应体 JSON 为 `{"status": "ok"}`

#### Scenario: 响应 Content-Type 为 JSON

- **WHEN** 客户端请求 `GET /health`
- **THEN** 响应 `Content-Type` 包含 `application/json`

### Requirement: FastAPI application entrypoint

系统 SHALL 提供可启动的 FastAPI 应用实例，并挂载 infra/health 路由。

#### Scenario: 应用可导入且包含 health 路由

- **WHEN** 测试客户端请求 `GET /health`
- **THEN** 请求由 FastAPI 应用处理并返回 Requirement: Health liveness endpoint 所定义的成功响应
