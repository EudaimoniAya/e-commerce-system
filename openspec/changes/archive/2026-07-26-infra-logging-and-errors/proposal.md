## Why

user/catalog/ordering 等业务域已交付，但 infra 层仍缺少结构化日志与统一错误响应契约：各 service 直接 `raise HTTPException`，错误 JSON 沿用 FastAPI 默认 `detail` 形态，日志无 request 关联字段，不利于本地排查、CI 诊断及后续 AI/机器读取。架构文档已规划 infra「公共异常」；`infra-database` change 亦预留结构化日志扩展。现需在继续扩展业务域之前补齐该横切能力。

## What Changes

- 引入 **loguru** 作为应用日志 API；通过 **InterceptHandler** 将 uvicorn/SQLAlchemy 等 stdlib logging 统一汇入 loguru sink
- 按 **`Settings.app_env`** 推导日志格式与级别：`development` 终端人类可读；`test`/`production` JSON；`test` 环境 level=WARNING 减少 pytest 噪音；`development`/`production` level=INFO
- 新增 **request_id middleware**：客户端可传 `X-Request-ID`，否则服务端生成 UUID；响应头回传；全请求生命周期 loguru `contextualize`（含 200 正常路径）
- 本地持久化 **`logs/app.log`**（JSON、`rotation` + `compression="gz"`）；`logs/` 已 gitignore；`test` 环境不写文件 sink
- 重构 **`app/main.py`** 为 **`create_app()`** 工厂；`register_exception_handlers(app)` 注册全局异常处理器
- **BREAKING**：所有 4xx/5xx 响应体统一为 `{"error": {"code", "message", "request_id"}}`（顶层键 `error`，不再使用 FastAPI 原生 `detail`）
- 单独 handler 处理 **`RequestValidationError`**（`code: VALIDATION_ERROR`，`message` 为 loc/msg 数组）；**`HTTPException`** 继续由业务层抛出，handler 解析 `code`：`detail` 为含 `code` 键的 dict 时取语义码，否则按 HTTP status 映射泛化码（如 422→`UNPROCESSABLE_ENTITY`）；未捕获 **`Exception`** 返回泛化 500 + 服务端全栈 log
- 迁移现有 integration 测试中 `detail` 断言；更新 **`user-auth`** spec 中错误格式表述
- 确认 **`.env.test`** 中 `APP_ENV=test`；**`.env.example`** 文档化日志相关约定
- 更新 **`docs/architecture.md`** 补充 `logging/`、`errors/` 模块说明

## Non-goals

- 不引入 domain exception 体系或大规模改写各域 `raise HTTPException`（允许将 `detail` 渐进升级为 `{"code": "...", "message": "..."}` 以提供语义化错误码）
- 不实现 OpenTelemetry、metrics、远程 log 平台、structlog
- 不修改各域业务规则（422/404/403 语义不变，仅错误 JSON 外壳变化）
- 不在本 change 为各域 service 新增业务 log 打点（Task 1 仅交付 infra 日志与 middleware，不涉及业务代码）
- 不实现按域分文件、CD 部署侧 log 采集配置
- 不使用 FastAPI `debug` 控制日志行为；500 响应不向客户端暴露 traceback

## Capabilities

### New Capabilities

- `infra-logging`: loguru 配置、InterceptHandler、request_id middleware、`logs/app.log` 持久化与按 `app_env` 切换格式/级别
- `infra-api-errors`: 统一 error JSON 契约、全局 exception handlers（HTTPException / RequestValidationError / Exception）、HTTPException 混合式 `code` 解析（dict detail 语义码或 status 泛化码）

### Modified Capabilities

- `user-auth`: 删除「响应 SHALL 为 FastAPI 格式（`detail` 字段）」表述；错误响应 SHALL 符合 `infra-api-errors`

## Impact

- **业务域**: `infra`（logging、errors、main 工厂）；测试断言批量更新；`user-auth` spec delta
- **新增/修改文件**: `app/main.py`、`app/infra/logging/`、`app/infra/errors/`、`pyproject.toml`（loguru）、`tests/infra/`、`.env.example`、`docs/architecture.md`；约 15 个 integration 测试文件错误断言迁移
- **API**: 所有错误响应 **BREAKING** 由 `{"detail": ...}` 变为 `{"error": {...}}`；成功响应不变；所有响应可选 `X-Request-ID` 头
- **依赖**: loguru
- **分支**: 基于 `dev` 的 `feature/infra-logging-and-errors`
