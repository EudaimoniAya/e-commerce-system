"""全局 exception handlers：统一 error JSON 契约。

三个 handler（注册顺序：具体 → 兜底）：
1. RequestValidationError → 422 + VALIDATION_ERROR
2. HTTPException → 原 status + 混合 code 解析（dict detail 语义码 或 status 泛化码）
3. Exception → 500 + INTERNAL_ERROR（不暴露 traceback）
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.infra.logging.middleware import get_request_id

# ── status → code 泛化映射 ────────────────────────────────────────

_STATUS_CODE_MAP: dict[int, str] = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
}


def _resolve_code(status_code: int, detail: object) -> tuple[str, object]:
    """HTTPException 混合式 code 解析（Decision 9）。

    - detail 为 dict 且含 "code" → 语义 code + message 键（缺省 ""）
    - 否则 → status 泛化码 + 原 detail
    """
    if isinstance(detail, dict) and "code" in detail:
        code = str(detail["code"])
        message = detail.get("message", "")
        return code, message

    code = _STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")
    return code, detail


# ── handlers ──────────────────────────────────────────────────────


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """RequestValidationError → 422 + VALIDATION_ERROR + Pydantic errors() 数组。"""
    logger.warning(
        "Validation error | {errors}",
        errors=exc.errors(),
        request_id=get_request_id(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": exc.errors(),
                "request_id": get_request_id(),
            }
        },
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """HTTPException → 原 status + 混合 code 解析。"""
    code, message = _resolve_code(exc.status_code, exc.detail)

    if exc.status_code >= 500:
        logger.error(
            "HTTP exception (5xx) | code={code} status={status}",
            code=code,
            status=exc.status_code,
            request_id=get_request_id(),
        )
    else:
        logger.warning(
            "HTTP exception | code={code} status={status}",
            code=code,
            status=exc.status_code,
            request_id=get_request_id(),
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": get_request_id(),
            }
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """未捕获 Exception → 500 + INTERNAL_ERROR，不暴露 traceback。"""
    logger.exception(
        "Unhandled exception | request_id={request_id}",
        request_id=get_request_id(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "request_id": get_request_id(),
            }
        },
    )
