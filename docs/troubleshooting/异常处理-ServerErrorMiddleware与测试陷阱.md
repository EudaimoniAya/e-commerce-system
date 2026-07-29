# 异常处理：ServerErrorMiddleware re-raise 与测试陷阱

## 场景

为 `infra/errors/` 编写统一异常处理：
- 注册三个 handler：RequestValidationError、HTTPException、未捕获 Exception
- 所有错误响应改为统一 error JSON 契约：`{error: {code, message, request_id}}`
- 使用 `httpx.AsyncClient`（基于 ASGITransport）编写测试验证 500 响应

## 问题 1：500 兜底 handler 不工作

### 现象

`test_500_code_is_internal_error` 等测试失败——httpx 不返回响应，而是直接抛出 `RuntimeError`。

```
RuntimeError: Unexpected failure
```

### 根因

`build_middleware_stack` 的分类逻辑把 `Exception` 分配给了 `ServerErrorMiddleware`：

```python
for key, value in self.exception_handlers.items():
    if key in (500, Exception):
        error_handler = value          # → ServerErrorMiddleware
```

`ServerErrorMiddleware` 的正确行为是：

1. 调用 handler → 生成 Response
2. 发送 Response
3. **`raise exc`** ← 始终 re-raise

源码注释说明：*"We always continue to raise the exception. This allows servers to log the error, or allows test clients to optionally raise the error within the test case."*

生产环境（uvicorn）接住 `raise exc` 并记录日志，客户端已收到响应。但 httpx.ASGITransport（默认 `raise_app_exceptions=True`）捕获 `raise exc` 后抛给测试代码，导致 `client.get("/raise-500")` 直接抛出异常，测试无法获取 `response` 对象。

### 解决

放弃 `app.add_exception_handler(Exception, handler)`，改用纯 ASGI middleware 在异常到达 ServerErrorMiddleware 之前截获：

```python
class UnhandledExceptionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        except (HTTPException, RequestValidationError):
            raise           # 交给 ExceptionMiddleware
        except Exception as exc:
            response = await unhandled_exception_handler(request, exc)
            await response(scope, receive, send)  # 不 re-raise
```

这样 ServerErrorMiddleware 收到的是正常 Response，不触发 re-raise。

### 继续保留 `add_exception_handler` 的 handler

```python
# 这些走 ExceptionMiddleware，行为正常
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
```

## 问题 2：request_id 在 500 响应中为空

### 现象

测试 `test_500_has_request_id` 通过（只断言 `"request_id" in body["error"]`），但真实值 test 中 `request_id` 为 `""`（ContextVar 默认值）。

### 根因

`@app.middleware("http")` 底层是 `BaseHTTPMiddleware`，它内部使用 `anyio.create_task_group()` 以子任务运行 `call_next`。当子任务抛出异常时，task group 的取消机制重置 ContextVar 到子任务创建时的快照。

```
RequestIDMiddleware（@app.middleware → BaseHTTPMiddleware）
  ContextVar.set("abc-123")            ← 父任务
  await call_next(request)             ← 子任务（anyio task group）
    UnhandledExceptionMiddleware（也是 @app.middleware）
      call_next → 路由抛 RuntimeError
    except: get_request_id() → ""      ← 子任务崩溃，ContextVar 回退
```

### 解决

将两个 `@app.middleware("http")` 中间件全部迁移为纯 ASGI class：

```python
class RequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # ... 设 ContextVar
        try:
            await self.app(scope, receive, send)   # ← 直接 await，无子任务
        finally:
            # ContextVar.reset 在同一个调用链上
```

```python
class UnhandledExceptionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)   # ← 直接 await，无子任务
        except Exception as exc:
            # get_request_id() → 读得到，因为 ContextVar 在同一个父任务作用域内
```

纯 ASGI 的 `await self.app(...)` 在同一 async 调用链上直接执行下一层，没有子任务边界，ContextVar 始终一致。

## 验证

全部 148 个测试通过，包括之前无法通过的 `request_id` 非空断言和 header-body 一致性断言。

## 关键教训

| 教训 | 内容 |
|------|------|
| `ServerErrorMiddleware` 必然 re-raise | 不是 bug，是设计意图——区分"向客户端发响应"和"向服务器报告"两个独立职责 |
| Exception 在框架内部有特殊路由 | build_middleware_stack 把 Exception 单独分给 ServerErrorMiddleware，不走 ExceptionMiddleware |
| `@app.middleware("http")` 有隐藏层 | BaseHTTPMiddleware + anyio task group 在异常路径下引入 ContextVar 丢失副作用 |
| 纯 ASGI middleware 没有隐藏层 | 直接 await self.app()，一切在掌控之中 |

## 相关知识

- `docs/decision/中间件栈与异常处理架构决策.md` — 对应的架构决策
- `app/infra/errors/handlers.py` — handler 实现
- `app/infra/errors/register.py` — 注册逻辑
- `app/infra/logging/middleware.py` — RequestIDMiddleware
