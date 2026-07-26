"""注册全局 exception handlers 与兜底 middleware 到 FastAPI app。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.infra.errors.handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


class UnhandledExceptionMiddleware:
    """纯 ASGI 兜底中间件：捕获未经 ExceptionMiddleware 处理的异常。

    设计为纯 ASGI（非 BaseHTTPMiddleware），避免 anyio.create_task_group()
    导致的 ContextVar 丢失，确保 error handler 内 get_request_id() 可正确读取。

    行为：
    - StarletteHTTPException / RequestValidationError → re-raise
      （ExceptionMiddleware 应已处理；若仍逃逸则交 ServerErrorMiddleware 兜底）
    - 其余 Exception → 调用 unhandled_exception_handler 返回统一 error JSON
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except (StarletteHTTPException, RequestValidationError):
            raise  # 交给更外层的 ServerErrorMiddleware 兜底
        except Exception as exc:
            request = Request(scope, receive)
            response = await unhandled_exception_handler(request, exc)
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局 exception handlers + 兜底 middleware。

    1. RequestValidationError → 422 + VALIDATION_ERROR（ExceptionMiddleware 处理）
    2. HTTPException → 原 status + 混合 code 解析（ExceptionMiddleware 处理）
    3. UnhandledExceptionMiddleware 兜底未捕获 Exception → 500 + INTERNAL_ERROR
       （纯 ASGI 中间件，位于 ExceptionMiddleware 与 ServerErrorMiddleware 之间）
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_middleware(UnhandledExceptionMiddleware)
