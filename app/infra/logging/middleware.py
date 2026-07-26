"""Request ID middleware：X-Request-ID 透传/生成，loguru contextualize 绑定。"""

import re
import uuid
from contextvars import ContextVar
from collections.abc import Awaitable, Callable

from loguru import logger
from starlette.requests import Request
from starlette.responses import Response

# 请求级 ContextVar，供 handler/service 安全读取当前 request_id
REQUEST_ID_CTX_VAR: ContextVar[str] = ContextVar("request_id", default="")

# X-Request-ID 合法性校验：strip 后长度 1–128，字符集 [A-Za-z0-9-_.]
_VALID_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-_.]{1,128}$")


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


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """透传或生成 X-Request-ID，绑定 loguru context 并回写响应头。

    1. 读取请求头 X-Request-ID → 合法则透传，否则生成 UUID4
    2. ContextVar 存储当前 request_id
    3. logger.contextualize 包裹下游（含 200 正常路径）
    4. 响应头回写 X-Request-ID
    """
    header_value = request.headers.get("X-Request-ID")
    if is_valid_request_id(header_value):
        request_id = header_value.strip()  # type: ignore[union-attr]
    else:
        request_id = str(uuid.uuid4())

    token = REQUEST_ID_CTX_VAR.set(request_id)
    try:
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)
    finally:
        REQUEST_ID_CTX_VAR.reset(token)

    response.headers["X-Request-ID"] = request_id
    return response
