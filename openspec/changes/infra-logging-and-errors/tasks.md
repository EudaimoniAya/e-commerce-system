## 1. 结构化日志、request_id 与 create_app（Task 1）

> 本 Task 仅交付 infra 日志与 middleware；**不**注册 exception handlers；**不**改各域 service 打点。

- [x] 1.1 `pyproject.toml` 增加 `loguru`；确认或补充 `.env.test` 中 `APP_ENV=test`；更新 `.env.example` 文档
- [x] 1.2 按 `specs/infra-logging/spec.md` 编写 `tests/infra/test_logging.py`（app_env 格式、X-Request-ID、logs/app.log、test 不写文件）；**不编写** 实现
- [x] 1.3 新增 `app/infra/logging/setup.py`（`setup_logging`、`InterceptHandler`、`app_env` 格式/级别、`logs/app.log` rotation+gzip）
- [x] 1.4 新增 `app/infra/logging/middleware.py`（`X-Request-ID` 透传/生成、`ContextVar`、`logger.contextualize`）
- [x] 1.5 重构 `app/main.py` 为 `create_app()`：调用 `setup_logging`、注册 request_id middleware、挂载既有路由；**暂不** 注册 exception handlers
- [x] 1.6 跑 `devbox run -- task ci` 确认 §1 测试通过（handler 未就绪前，错误响应仍为 FastAPI 默认 `detail` 可接受）

## 2. 统一异常处理与测试迁移（Task 2）

> **BREAKING**：错误 JSON 由 `detail` 变为 `error`；一次性迁移测试断言；默认不改 service 的 `HTTPException`（handler 对字符串 detail 按 status 映射泛化 code，dict detail 可含语义 code）。

- [x] 2.1 按 `specs/infra-api-errors/spec.md` 编写 `tests/infra/test_error_handlers.py`（ValidationError、HTTPException 混合 code 解析、500 泛化、request_id）；**不编写** handlers
- [x] 2.2 新增 `app/infra/errors/handlers.py` 与 `register.py`（三个 handler + HTTP status 泛化码/dict detail 语义码映射 + 结构化 error log）
- [x] 2.3 `create_app()` 调用 `register_exception_handlers(app)`
- [x] 2.4 迁移 integration 测试中 `detail` 断言为 `error` 结构（grep `tests/**/*.py`）；含 `test_my_products.py` 精确断言
- [x] 2.5 跑 `devbox run -- task ci` 全绿

## 3. 文档与收尾（Task 3）

- [ ] 3.1 更新 `docs/architecture.md`：补充 `infra/logging/`、`infra/errors/`、`create_app` 说明
- [ ] 3.2 archive change 并 sync specs（`infra-logging`、`infra-api-errors`、`user-auth` delta）
