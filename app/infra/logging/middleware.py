"""Request ID middleware：X-Request-ID 透传/生成，loguru contextualize 绑定。"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from contextvars import ContextVar

from loguru import logger
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 请求级 ContextVar，供 handler/service 安全读取当前 request_id
REQUEST_ID_CTX_VAR: ContextVar[str] = ContextVar("request_id", default="")

# X-Request-ID 合法性校验：strip 后长度 1–128，字符集 [A-Za-z0-9-_.]
_VALID_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-_.]{1,128}$")

# ASGI header key
_X_REQUEST_ID_HEADER: bytes = b"x-request-id"


def get_request_id() -> str:
    """返回当前请求的 request_id（安全读取 ContextVar）。"""
    return REQUEST_ID_CTX_VAR.get()


def is_valid_request_id(value: str | None) -> bool:
    """校验 X-Request-ID 头值是否合法。

    合法条件：
    - 非 None
    - strip() 后长度 1~128
    - 仅含 [A-Za-z0-9-_.]
    """
    if value is None:
        return False
    stripped = value.strip()
    return bool(_VALID_REQUEST_ID_RE.fullmatch(stripped))


def _extract_header(scope: Scope, key: bytes) -> str | None:
    """从 ASGI scope headers 中按 key（大小写不敏感）提取首值。"""
    raw_headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", [])
    key_lower = key.lower()
    for name, value in raw_headers:
        if name.lower() == key_lower:
            return value.decode("latin-1")
    return None


class RequestIDMiddleware:
    """纯 ASGI 中间件：透传或生成 X-Request-ID，绑定 loguru context 并回写响应头。

    设计为纯 ASGI（非 BaseHTTPMiddleware），以避免 anyio.create_task_group()
    导致的 ContextVar 丢失问题。

    Lifecycle：
    1. 读取请求头 X-Request-ID → 合法则透传，否则生成 UUID4
    2. ContextVar 存储当前 request_id
    3. logger.contextualize 包裹下游
    4. send wrapper 注入 X-Request-ID 响应头
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. 确定 request_id
        header_value = _extract_header(scope, _X_REQUEST_ID_HEADER)
        if is_valid_request_id(header_value):
            request_id = header_value.strip()  # type: ignore[union-attr]
        else:
            request_id = str(uuid.uuid4())

        # 2. 注入响应头（send wrapper）
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append((_X_REQUEST_ID_HEADER, request_id.encode()))
                message["headers"] = headers
            await send(message)

        # 3. ContextVar + loguru 绑定，围绕整个下游
        token = REQUEST_ID_CTX_VAR.set(request_id)
        try:
            with logger.contextualize(request_id=request_id):
                await self.app(scope, receive, send_wrapper)
        finally:
            REQUEST_ID_CTX_VAR.reset(token)
