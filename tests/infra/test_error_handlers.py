"""infra/errors 统一异常处理测试（TDD 红阶段）。

本文件仅编写测试用例；exception handlers 与 register 函数在 Task 2.2 实现。
"""

import allure
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel


# ── 测试用 Pydantic model ─────────────────────────────────────────


class _TestItem(BaseModel):
    name: str
    price: float


# ── fixture：最小测试 app，已注册 handlers ────────────────────────


@pytest.fixture
def app_with_handlers() -> FastAPI:
    """创建最小 FastAPI app，注册 request_id middleware 与 exception handlers。

    提供 5 条测试路由：
    - POST /items                → 触发 RequestValidationError（422）
    - GET  /raise-http/{status}  → 触发 HTTPException（任意 status，字符串 detail）
    - GET  /raise-http-dict      → 触发 HTTPException（dict detail 含 code/message）
    - GET  /raise-500            → 触发未捕获 RuntimeError（500）
    - GET  /ok                   → 200 成功响应
    """
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.infra.errors.register import register_exception_handlers
    from app.infra.logging.middleware import RequestIDMiddleware

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    @app.post("/items")
    async def create_item(item: _TestItem) -> dict[str, str]:
        return {"name": item.name}

    @app.get("/raise-http/{status}")
    async def raise_http(status: int) -> None:
        raise StarletteHTTPException(status_code=status, detail="Something went wrong")

    @app.get("/raise-http-dict")
    async def raise_http_dict() -> None:
        raise StarletteHTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "Invalid phone or password",
            },
        )

    @app.get("/raise-500")
    async def raise_500() -> None:
        raise RuntimeError("Unexpected failure")

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.fixture
async def client_with_handlers(app_with_handlers: FastAPI) -> AsyncClient:
    """基于 app_with_handlers 的 httpx AsyncClient。"""
    transport = ASGITransport(app=app_with_handlers)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ── 1. 统一 error JSON 契约 ──────────────────────────────────────


class TestErrorResponseEnvelope:
    """spec: Unified error response envelope — 顶层键 error，非 detail。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("校验失败时响应体顶层为 error，不存在 detail")
    async def test_422_has_error_not_detail(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """校验失败时响应体顶层为 error，不存在 detail。"""
        response = await client_with_handlers.post(
            "/items",
            json={"name": 123, "price": "not-a-number"},
        )
        assert response.status_code == 422
        body = response.json()
        assert "error" in body, "错误响应应包含 error 键"
        assert "detail" not in body, "不应使用 FastAPI 默认 detail 键"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("error 对象包含 code、message、request_id 三个字段")
    async def test_error_object_has_code_message_request_id(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """error 对象包含 code、message、request_id 三个字段。"""
        response = await client_with_handlers.get("/raise-http/404")
        body = response.json()
        error = body["error"]
        assert "code" in error
        assert "message" in error
        assert "request_id" in error
        assert isinstance(error["code"], str)
        assert error["request_id"] != ""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("200 成功响应不应包含 error 对象")
    async def test_2xx_response_does_not_have_error(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """200 成功响应不应包含 error 对象。"""
        response = await client_with_handlers.get("/ok")
        assert response.status_code == 200
        body = response.json()
        assert "error" not in body, "成功响应不应包含 error"


# ── 2. RequestValidationError handler ─────────────────────────────


class TestValidationErrorHandler:
    """spec: RequestValidationError handler — 422，code=VALIDATION_ERROR。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("请求体校验失败 → code=VALIDATION_ERROR")
    async def test_validation_error_code_is_validation_error(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """请求体校验失败 → code=VALIDATION_ERROR。"""
        response = await client_with_handlers.post(
            "/items",
            json={"name": 123},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("校验错误 message 为 Pydantic errors() 数组")
    async def test_validation_error_message_is_array(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """校验错误 message 为 Pydantic errors() 数组（含 loc/msg/type）。"""
        response = await client_with_handlers.post(
            "/items",
            json={"name": 123, "price": "not-a-number"},
        )
        body = response.json()
        message = body["error"]["message"]
        assert isinstance(message, list), "校验错误 message 应为数组"
        assert len(message) >= 1
        first = message[0]
        assert "loc" in first or "msg" in first, "数组元素应含 loc/msg/type"


# ── 3. HTTPException handler — 混合式 code 解析 ───────────────────


class TestHTTPExceptionCodeResolution:
    """spec: HTTPException handler with mixed code resolution。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("字符串 detail → code 按 status 映射泛化码")
    async def test_string_detail_maps_status_to_generic_code(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """字符串 detail → code 按 status 映射泛化码。"""
        response = await client_with_handlers.get("/raise-http/422")
        body = response.json()
        assert response.status_code == 422
        assert body["error"]["code"] == "UNPROCESSABLE_ENTITY"
        assert body["error"]["message"] == "Something went wrong"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("dict detail 含 code → 使用语义 code")
    async def test_dict_detail_uses_semantic_code(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """dict detail 含 code → 使用语义 code。"""
        response = await client_with_handlers.get("/raise-http-dict")
        body = response.json()
        assert response.status_code == 422
        assert body["error"]["code"] == "INVALID_CREDENTIALS"
        assert body["error"]["message"] == "Invalid phone or password"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("404 → code=NOT_FOUND")
    async def test_404_maps_to_not_found(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """404 → code=NOT_FOUND。"""
        response = await client_with_handlers.get("/raise-http/404")
        body = response.json()
        assert response.status_code == 404
        assert body["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("401 → code=UNAUTHORIZED")
    async def test_401_maps_to_unauthorized(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """401 → code=UNAUTHORIZED。"""
        response = await client_with_handlers.get("/raise-http/401")
        body = response.json()
        assert response.status_code == 401
        assert body["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("403 → code=FORBIDDEN")
    async def test_403_maps_to_forbidden(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """403 → code=FORBIDDEN。"""
        response = await client_with_handlers.get("/raise-http/403")
        body = response.json()
        assert body["error"]["code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("409 → code=CONFLICT")
    async def test_409_maps_to_conflict(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """409 → code=CONFLICT。"""
        response = await client_with_handlers.get("/raise-http/409")
        body = response.json()
        assert body["error"]["code"] == "CONFLICT"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("非标准 4xx → code=HTTP_418")
    async def test_unknown_4xx_uses_http_prefix_code(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """非标准 4xx（如 418） → code=HTTP_418。"""
        response = await client_with_handlers.get("/raise-http/418")
        body = response.json()
        assert body["error"]["code"] == "HTTP_418"


# ── 4. 未捕获异常 handler ─────────────────────────────────────────


class TestUnhandledExceptionHandler:
    """spec: Unhandled exception handler — 500，code=INTERNAL_ERROR，不暴露 traceback。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("未捕获异常 → 500，code=INTERNAL_ERROR")
    async def test_500_code_is_internal_error(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """未捕获异常 → 500，code=INTERNAL_ERROR。"""
        response = await client_with_handlers.get("/raise-500")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("500 message 为泛化文案，不暴露 traceback")
    async def test_500_message_is_generic(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """500 message 为泛化文案，不暴露 traceback 或异常消息。"""
        response = await client_with_handlers.get("/raise-500")
        body = response.json()
        message = body["error"]["message"]
        assert "Unexpected failure" not in str(message), "不应暴露原始异常消息"
        assert "Traceback" not in str(message), "不应暴露 Python traceback"
        assert isinstance(message, str)
        assert len(message) > 0

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("500 响应仍包含 request_id 字段")
    async def test_500_has_request_id(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """500 响应仍包含 request_id 字段。"""
        response = await client_with_handlers.get("/raise-500")
        body = response.json()
        assert "request_id" in body["error"], "500 响应应含 request_id 字段"


# ── 5. request_id 一致性 ──────────────────────────────────────────


class TestErrorRequestId:
    """spec: Error responses include request_id aligned with middleware。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("error.request_id 与响应头 X-Request-ID 一致")
    async def test_error_request_id_matches_response_header(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """error.request_id 与响应头 X-Request-ID 一致。"""
        response = await client_with_handlers.get("/raise-http/422")
        body = response.json()
        header_id = response.headers.get("x-request-id")
        body_id = body["error"]["request_id"]
        assert header_id is not None, "响应头应包含 X-Request-ID"
        assert (
            body_id == header_id
        ), f"body request_id ({body_id}) 应与 header ({header_id}) 一致"

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("422 校验错误也包含 request_id")
    async def test_validation_error_has_request_id(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """422 校验错误也包含 request_id。"""
        response = await client_with_handlers.post(
            "/items",
            json={"name": 123},
        )
        body = response.json()
        assert body["error"]["request_id"] != ""
        assert body["error"]["request_id"] == response.headers.get("x-request-id")


# ── 6. HTTP status 保留 ───────────────────────────────────────────


class TestHTTPStatusPreserved:
    """HTTPException handler 保留业务层设置的 HTTP status。"""

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("error_handlers")
    @allure.title("HTTPException 的 status_code 原样保留")
    async def test_status_code_preserved(
        self,
        client_with_handlers: AsyncClient,
    ) -> None:
        """HTTPException 的 status_code 原样保留。"""
        for status in (400, 401, 403, 404, 409, 422):
            response = await client_with_handlers.get(f"/raise-http/{status}")
            assert response.status_code == status, f"status {status} 应被保留"
