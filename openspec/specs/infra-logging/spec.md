# infra-logging

## Purpose

infra 横切结构化日志：loguru 配置、InterceptHandler 统一 stdlib 输出、request_id middleware、按 `app_env` 切换格式/级别及本地 `logs/app.log` 持久化。

## Requirements

### Requirement: Structured logging via loguru

系统 SHALL 使用 **loguru** 作为应用日志 API；SHALL 在应用启动时调用 `setup_logging(settings)` 配置 sink，且 SHALL NOT 依赖裸 stdlib logging 作为业务代码入口。

#### Scenario: 业务代码使用 loguru logger

- **WHEN** infra 或业务模块执行 `from loguru import logger` 并写入日志
- **THEN** 日志 SHALL 经 loguru 配置的 sink 输出

### Requirement: InterceptHandler unifies stdlib logging

系统 SHALL 提供 `InterceptHandler`（继承 `logging.Handler`），将 uvicorn、SQLAlchemy 等 stdlib `LogRecord` 转入 loguru，使全进程日志格式一致。

#### Scenario: uvicorn 日志与 loguru 格式一致

- **WHEN** 应用在 `app_env=development` 下启动且 uvicorn 写入 access/error 日志
- **THEN** 终端输出 SHALL 经同一 loguru sink 格式化（非独立 stdlib Formatter 风格）

### Requirement: Log format and level derived from app_env

系统 SHALL 根据 `Settings.app_env` 推导日志格式与最低级别，且 SHALL NOT 使用 FastAPI `debug` 控制日志行为。

#### Scenario: development 终端人类可读

- **WHEN** `app_env` 为 `development`
- **THEN** stderr sink SHALL 使用人类可读格式
- **AND** 最低级别 SHALL 为 INFO

#### Scenario: test 环境 JSON 且 WARNING 以上

- **WHEN** `app_env` 为 `test`
- **THEN** stderr sink SHALL 使用 JSON（`serialize=True` 或等价）
- **AND** 最低级别 SHALL 为 WARNING

#### Scenario: production JSON 且 INFO

- **WHEN** `app_env` 为 `production`
- **THEN** stderr sink SHALL 使用 JSON
- **AND** 最低级别 SHALL 为 INFO

### Requirement: Local persistent log file

系统 SHALL 在 `development` 与 `production` 环境写入本地文件 `logs/app.log`（JSON 每行一条）；SHALL 启用 rotation（如 `10 MB`）与 `compression="gz"`；启动时 SHALL 确保 `logs/` 目录存在；`test` 环境 SHALL NOT 写入该文件。

#### Scenario: development 写入 logs/app.log

- **WHEN** 应用在 `app_env=development` 下处理至少一次 HTTP 请求
- **THEN** 项目根目录 `logs/app.log` SHALL 存在且包含可解析的 JSON 行

#### Scenario: test 不写文件

- **WHEN** 测试在 `app_env=test` 下运行 pytest
- **THEN** SHALL NOT 要求 `logs/app.log` 存在或增长

### Requirement: Request ID middleware

系统 SHALL 提供 HTTP middleware，为每个请求关联 `request_id`：若请求头 `X-Request-ID` 存在且通过合法校验则沿用，否则生成 UUID4；SHALL 在请求生命周期内通过 loguru `contextualize` 绑定；SHALL 在响应头 `X-Request-ID` 回传。

#### Scenario: 无客户端 ID 时服务端生成

- **WHEN** 客户端请求任意端点且未携带 `X-Request-ID`
- **THEN** 响应 SHALL 包含头 `X-Request-ID`
- **AND** 其值 SHALL 为非空字符串

#### Scenario: 客户端透传合法 ID

- **WHEN** 客户端携带合法 `X-Request-ID: client-req-001`
- **THEN** 响应头 `X-Request-ID` SHALL 为 `client-req-001`

#### Scenario: 成功响应路径日志含 request_id

- **WHEN** 客户端请求 `GET /health` 且返回 200
- **THEN** 该请求产生的 loguru 日志记录 SHALL 包含字段 `request_id`（与响应头一致）

### Requirement: Test environment APP_ENV

`.env.test`（由 `APP_ENV_FILE=.env.test` 加载）SHALL 设置 `APP_ENV=test`；`.env.example` SHALL 文档化该约定。

#### Scenario: task test 使用 test 日志 profile

- **WHEN** 执行 `task test` 或 CI pytest
- **THEN** 运行时 `Settings.app_env` SHALL 为 `test`

### Requirement: Logging setup invoked from create_app

系统 SHALL 在 `create_app()` 内、挂载路由之前调用 `setup_logging(settings)` 与 request_id middleware 注册。

#### Scenario: 应用工厂配置日志

- **WHEN** 测试或 uvicorn 导入 `app.main:app`
- **THEN** 应用 SHALL 经 `create_app()` 创建且 logging 已配置
