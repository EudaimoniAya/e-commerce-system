## Context

`bootstrap-engineering-shell`、`infra-database`、`user-auth` 及 catalog/ordering 业务域已交付。当前 `app/main.py` 直接实例化 `FastAPI`，无全局 exception handler；各域 service 使用 `HTTPException`，错误响应为 FastAPI 默认 `{"detail": ...}`；应用日志未结构化，无 request 关联字段。`docs/architecture.md` 规划 infra「公共异常」；`.gitignore` 已包含 `logs/`。

约束：

- infra **不得** import 任何业务域模块
- 测试：`task test` 通过 `APP_ENV_FILE=.env.test` 加载配置；integration 测试使用 `AsyncClient`
- 数据库/CI 命令须 `devbox run --` 包装（与既有纪律一致）

## Goals / Non-Goals

**Goals:**

- 提供 loguru 结构化日志（终端 + `logs/app.log`），InterceptHandler 统一 stdlib 与业务输出
- 提供 request_id middleware（客户端 `X-Request-ID` 可透传）
- 提供统一 error JSON 契约与全局 exception handlers（HTTPException 混合式 code 解析，见 Decision 9）
- `create_app()` 工厂组装应用
- 迁移 integration 测试错误断言；更新 `user-auth` spec delta

**Non-Goals:**

- domain exception 体系、OpenTelemetry、metrics、structlog、远程 log 平台
- 本 change 为各域 service 新增业务 log 打点
- 按域分 log 文件；500 响应向客户端暴露 traceback
- 大规模改写现有 `raise HTTPException`（允许渐进将 `detail` 改为含 `code`/`message` 的 dict）

## Decisions

### 1. 日志库：loguru + InterceptHandler

**选择**：业务与 infra 使用 `from loguru import logger`；`InterceptHandler(logging.Handler)` 将 uvicorn/SQLAlchemy 等 stdlib 日志转入 loguru。

**理由**：较 stdlib logging 配置更简；原生支持 JSON serialize、contextualize、rotation/compression。

**备选**：纯 stdlib + JSON Formatter（样板多）；structlog（本阶段过重）。

### 2. 格式与级别：由 `Settings.app_env` 推导

| `app_env` | stderr 格式 | stderr level | `logs/app.log` |
|-----------|-------------|--------------|----------------|
| `development` | 人类可读 | INFO | JSON（`serialize=True`） |
| `test` | JSON | WARNING | 不启用 |
| `production` | JSON | INFO | JSON + rotation + gzip |

**理由**：test WARNING 减少 pytest capture 噪音；dev 终端可读、文件 JSON 便于事后检索；不使用 FastAPI `debug` 控制日志。

**`.env.test`**：Task 1 确认或补充 `APP_ENV=test`；`.env.example` 文档化。

### 3. 本地文件 sink：`logs/app.log`

```python
logger.add(
    "logs/app.log",
    rotation="10 MB",
    compression="gz",
    serialize=True,
    level="INFO",
    enqueue=True,
)
```

启动时 `Path("logs").mkdir(exist_ok=True)`。`logs/` 已 gitignore。

**理由**：用户可在本地查看 JSON 日志验证 error/request_id 形态；loguru 内置 rotation/compression，无需自写脚本。

### 4. request_id middleware

**选择**：

- 读取请求头 `X-Request-ID`；若缺失或非空合法字符串则服务端生成 UUID4
- 合法：`strip()` 后长度 1–128，字符集 `[A-Za-z0-9-_.]`（简单校验，防注入/log 污染）
- `ContextVar` + `logger.contextualize(request_id=...)` 包裹 `call_next`
- 响应头回写 `X-Request-ID`

**理由**：客户端已传合法 `X-Request-ID` 时沿用该值，便于联调、网关透传与上游 log 关联；正常 200 路径日志亦带 request_id。

### 5. 应用工厂：`create_app()`

```text
app/main.py
├── create_app() -> FastAPI
│   ├── get_settings()
│   ├── setup_logging(settings)
│   ├── app = FastAPI(...)
│   ├── register_middleware(app)      # request_id
│   ├── register_exception_handlers(app)
│   └── include_router(...)
└── app = create_app()                # uvicorn 入口不变
```

**理由**：`register_exception_handlers(app)` 在工厂内调用，函数体内用 `@app.exception_handler` 注册各处理器；测试可独立建 app；main 仅负责组装。

### 6. 模块布局

```text
app/infra/
├── logging/
│   ├── setup.py          # setup_logging, InterceptHandler
│   └── middleware.py     # request_id_middleware, ContextVar
└── errors/
    ├── handlers.py       # 各 handler 实现、build_error_body、resolve_code
    └── register.py       # register_exception_handlers(app)

tests/infra/
├── test_logging.py
└── test_error_handlers.py
```

infra **不** import 业务域；handlers 仅处理 FastAPI/Starlette 异常类型。

### 7. 统一 error JSON 契约

所有 **4xx/5xx** 响应体：

```json
{
  "error": {
    "code": "UNPROCESSABLE_ENTITY",
    "message": "Invalid email or password",
    "request_id": "8f3a2b1c-..."
  }
}
```

| 字段 | 规则 |
|------|------|
| `error` | 顶层固定键（**不用** FastAPI `detail`） |
| `code` | 字符串；见 Decision 9（HTTPException 混合解析）与固定码表 |
| `message` | `str` 或 `list`（校验错误为 loc/msg 数组） |
| `request_id` | 必填，与 middleware / 响应头一致 |

### 8. Exception handlers（注册顺序：具体 → 兜底）

| 异常类型 | HTTP | `code` | `message` | 服务端 log |
|----------|------|--------|-----------|------------|
| `RequestValidationError` | 422 | `VALIDATION_ERROR` | Pydantic `errors()` 数组 | WARNING |
| `HTTPException` | `exc.status_code` | dict detail 语义码或 status 泛化码 | `detail` 字符串/list 或 dict 的 `message` | WARNING（4xx）/ ERROR（5xx） |
| `Exception` | 500 | `INTERNAL_ERROR` | `"Internal server error"` | `logger.exception` |

**500 响应**：三环境均泛化文案，不向客户端暴露 traceback。

### 9. HTTPException 混合式 `code` 解析

1. 若 `detail` 为 `dict` 且含 `"code"`：`code = detail["code"]`，`message = detail.get("message", detail)`（`message` 键缺失时 fallback 整 dict 或空串——implement 时优先要求 `message` 键）
2. 否则：`message = detail`（str 或 list），`code` 按 status 映射：

| status | code |
|--------|------|
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 409 | `CONFLICT` |
| 422 | `UNPROCESSABLE_ENTITY` |
| 其他 4xx/5xx | `HTTP_{status}`（如 `HTTP_418`） |

Task 2 **默认不改**各域 service；重要错误可渐进改为 `detail={"code": "INVALID_CREDENTIALS", "message": "..."}`。

### 10. 测试迁移范围

- grep `"detail"` in `tests/**/*.py`（约 15 处）改为断言 `error` 结构
- 精确断言如 `{"detail": "Shop not found"}` 改为 `error.message` + `error.code`
- `user-auth` spec delta：三处「`detail` 字段」改为「符合 `infra-api-errors`」
- 新增 `tests/infra/test_logging.py`、`tests/infra/test_error_handlers.py`

## Risks / Trade-offs

- **[Risk] BREAKING 错误 JSON** → Task 2 一次性迁移测试；业务 status 语义不变
- **[Risk] 初期 `detail` 多为字符串，error.code 多为 status 泛化码** → 重要错误可渐进改为 dict detail；`message` 始终来自业务文案
- **[Risk] loguru 与 uvicorn 双通道** → InterceptHandler + `logging.basicConfig(..., force=True)` 单 sink
- **[Risk] `logs/app.log` 磁盘增长** → rotation 10MB + gzip；retention 可选后续加
- **[Risk] test WARNING 掩盖 INFO 诊断** → 失败用例仍可见 ERROR；调试时用 `-s` 或临时调 level

## Migration Plan

1. **Task 1**：loguru + middleware + 文件 sink；`create_app` 骨架（handlers 可 stub 或尚未注册）；infra 日志测试
2. **Task 2**：注册 handlers；迁移全量测试；`user-auth` spec delta
3. **Task 3**：`docs/architecture.md`；archive + sync specs
4. **Rollback**：revert change；错误 JSON 恢复 `detail`（需同步 revert 测试）

## Open Questions

（无。）
