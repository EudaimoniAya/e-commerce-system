# infra-api-errors

## Purpose

infra 横切统一 API 错误响应契约：所有 4xx/5xx 返回 `{"error": {"code", "message", "request_id"}}`；全局 exception handlers 处理校验错误、HTTPException 与未捕获异常；错误路径结构化日志。

## Requirements

### Requirement: Unified error response envelope

所有 HTTP **4xx** 与 **5xx** 响应体 SHALL 使用统一结构，顶层键 SHALL 为 `error`（SHALL NOT 使用 FastAPI 默认顶层 `detail`）：

```json
{
  "error": {
    "code": "<string>",
    "message": "<string-or-array>",
    "request_id": "<string>"
  }
}
```

#### Scenario: 错误响应包含 error 对象

- **WHEN** API 返回任意 4xx 或 5xx
- **THEN** 响应体 JSON SHALL 包含对象键 `error`
- **AND** `error` SHALL 包含键 `code`、`message`、`request_id`

#### Scenario: 成功响应不使用 error  envelope

- **WHEN** API 返回 2xx
- **THEN** 响应体 SHALL NOT 要求包含 `error` 对象

### Requirement: RequestValidationError handler

系统 SHALL 为 `RequestValidationError` 注册独立 exception handler；HTTP 状态码 SHALL 为 **422**；`error.code` SHALL 为 **`VALIDATION_ERROR`**；`error.message` SHALL 为 Pydantic/FastAPI 校验错误数组（含 `loc`、`msg`、`type` 等字段）。

#### Scenario: 请求体校验失败

- **WHEN** 客户端提交不符合 schema 的 JSON body（如 password 长度不足）
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.code` SHALL 为 `VALIDATION_ERROR`
- **AND** `error.message` SHALL 为 array
- **AND** `error.request_id` SHALL 非空

### Requirement: HTTPException handler with mixed code resolution

系统 SHALL 为 `HTTPException` 注册 exception handler，保留原 HTTP 状态码，并按以下规则解析 `code` 与 `message`（混合式）：

1. 若 `detail` 为 `dict` 且含 `"code"`：`error.code = detail["code"]`，`error.message = detail["message"]`（当 `message` 键存在）
2. 否则：`error.message = detail`（str 或 list），`error.code` 按 status 映射：`401→UNAUTHORIZED`，`403→FORBIDDEN`，`404→NOT_FOUND`，`409→CONFLICT`，`422→UNPROCESSABLE_ENTITY`，其他 `HTTP_{status}`

#### Scenario: 字符串 detail 映射泛化 code

- **WHEN** service 抛出 `HTTPException(status_code=422, detail="Invalid email or password")`
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.code` SHALL 为 `UNPROCESSABLE_ENTITY`
- **AND** `error.message` SHALL 为 `"Invalid email or password"`

#### Scenario: dict detail 使用语义 code

- **WHEN** service 抛出 `HTTPException(status_code=422, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"})`
- **THEN** `error.code` SHALL 为 `INVALID_CREDENTIALS`
- **AND** `error.message` SHALL 为 `"Invalid email or password"`

#### Scenario: 404 业务错误

- **WHEN** service 抛出 `HTTPException(status_code=404, detail="Shop not found")`
- **THEN** `error.code` SHALL 为 `NOT_FOUND`
- **AND** `error.message` SHALL 为 `"Shop not found"`

### Requirement: Unhandled exception handler

系统 SHALL 为未捕获的 `Exception` 注册兜底 handler；HTTP 状态码 SHALL 为 **500**；`error.code` SHALL 为 **`INTERNAL_ERROR`**；`error.message` SHALL 为泛化文案（如 `"Internal server error"`）；SHALL NOT 向客户端返回 traceback；服务端 SHALL 使用 `logger.exception` 记录完整堆栈。

#### Scenario: 未预期异常

- **WHEN** 路由或 service 抛出非 HTTPException、非 RequestValidationError 的异常
- **THEN** 响应状态码 SHALL 为 500
- **AND** `error.code` SHALL 为 `INTERNAL_ERROR`
- **AND** `error.message` SHALL NOT 包含 Python traceback 文本

### Requirement: Error responses include request_id aligned with middleware

所有 error handler 输出的 `error.request_id` SHALL 与当前请求的 request_id middleware 值一致，且 SHALL 与响应头 `X-Request-ID` 一致（当 middleware 已启用）。

#### Scenario: 422 错误含 request_id

- **WHEN** 客户端触发业务 422 错误
- **THEN** `error.request_id` SHALL 等于响应头 `X-Request-ID`

### Requirement: Exception handlers registered via factory

系统 SHALL 在 `register_exception_handlers(app)` 内注册上述 handlers，并由 `create_app()` 调用；handler 实现 SHALL 位于 `app/infra/errors/`，且 SHALL NOT import 任何业务域模块。

#### Scenario: 应用挂载全局 handlers

- **WHEN** 测试客户端触发 `RequestValidationError` 或 `HTTPException`
- **THEN** 响应 SHALL 符合本 spec 的 `error` 结构（非 FastAPI 默认 `detail` 顶层）

### Requirement: Error path structured logging

当 exception handler 处理 4xx/5xx 时，SHALL 写入结构化 log（含 `request_id`、`code`、HTTP status）；500 SHALL 使用 exception 级别记录堆栈。

#### Scenario: HTTP 422 记录 warning 日志

- **WHEN** HTTPException handler 处理 422
- **THEN** SHALL 写入 level ≥ WARNING 的 loguru 日志且含 `request_id`
