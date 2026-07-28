## MODIFIED Requirements

### Requirement: HTTPException handler with mixed code resolution

系统 SHALL 为 `HTTPException` 注册 exception handler，保留原 HTTP 状态码，并按以下规则解析 `code` 与 `message`（混合式）：

1. 若 `detail` 为 `dict` 且含 `"code"`：`error.code = detail["code"]`，`error.message = detail["message"]`（当 `message` 键存在）
2. 否则：`error.message = detail`（str 或 list），`error.code` 按 status 映射：`401→UNAUTHORIZED`，`403→FORBIDDEN`，`404→NOT_FOUND`，`409→CONFLICT`，`422→UNPROCESSABLE_ENTITY`，其他 `HTTP_{status}`

#### Scenario: 字符串 detail 映射泛化 code

- **WHEN** service 抛出 `HTTPException(status_code=422, detail="Invalid phone or password")`
- **THEN** 响应状态码 SHALL 为 422
- **AND** `error.code` SHALL 为 `UNPROCESSABLE_ENTITY`
- **AND** `error.message` SHALL 为 `"Invalid phone or password"`

#### Scenario: dict detail 使用语义 code

- **WHEN** service 抛出 `HTTPException(status_code=422, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid phone or password"})`
- **THEN** `error.code` SHALL 为 `INVALID_CREDENTIALS`
- **AND** `error.message` SHALL 为 `"Invalid phone or password"`

#### Scenario: 404 业务错误

- **WHEN** service 抛出 `HTTPException(status_code=404, detail="Shop not found")`
- **THEN** `error.code` SHALL 为 `NOT_FOUND`
- **AND** `error.message` SHALL 为 `"Shop not found"`
