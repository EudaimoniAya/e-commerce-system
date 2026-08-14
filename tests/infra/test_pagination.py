"""infra/pagination 单元测试。

覆盖：
- PaginationParams 为 Pydantic BaseModel（禁止 tuple）
- Paginated[TResponse] 泛型分页响应壳序列化
- FastAPI Query 边界校验（200 / 422）

约束：无需 MySQL/Redis，不依赖 tests.testkit 或 HTTP client fixture。
"""

from __future__ import annotations

import allure
import pytest
from pydantic import BaseModel, ConfigDict

# ═══════════════════════════════════════════════════════════════════════
# PaginationParams
# ═══════════════════════════════════════════════════════════════════════


class TestPaginationParams:
    """PaginationParams SHALL 为 Pydantic BaseModel，禁止为 tuple。"""

    def test_is_pydantic_model_not_tuple(self) -> None:
        """PaginationParams SHALL 为 Pydantic BaseModel，禁止返回 tuple。"""
        from app.infra.pagination.schemas import PaginationParams  # noqa: E402

        params = PaginationParams(limit=20, offset=0)
        assert isinstance(params, BaseModel)
        assert not isinstance(params, tuple)

    def test_attribute_access_limit_offset(self) -> None:
        """Router 以 params.limit / params.offset 属性访问。"""
        from app.infra.pagination.schemas import PaginationParams  # noqa: E402

        params = PaginationParams(limit=10, offset=5)
        assert params.limit == 10
        assert params.offset == 5

    @pytest.mark.parametrize(
        "limit,offset",
        [
            (1, 0),
            (100, 0),
            (20, 10000),
            (1, 999999),
        ],
    )
    def test_valid_boundaries(self, limit: int, offset: int) -> None:
        """边界值应成功构造 PaginationParams（Query 层已在外部校验）。"""
        from app.infra.pagination.schemas import PaginationParams  # noqa: E402

        params = PaginationParams(limit=limit, offset=offset)
        assert params.limit == limit
        assert params.offset == offset

    def test_model_dump(self) -> None:
        """PaginationParams 可序列化为 dict。"""
        from app.infra.pagination.schemas import PaginationParams  # noqa: E402

        params = PaginationParams(limit=15, offset=30)
        d = params.model_dump()
        assert d == {"limit": 15, "offset": 30}


# ═══════════════════════════════════════════════════════════════════════
# Paginated[TResponse]
# ═══════════════════════════════════════════════════════════════════════


class TestPaginatedResponse:
    """Paginated[TResponse] 泛型分页响应壳。"""

    def test_paginated_with_items(self) -> None:
        """Paginated 包含 items / total / limit / offset 四个字段。"""
        from app.infra.pagination.schemas import Paginated  # noqa: E402

        result = Paginated[str](
            items=["a", "b", "c"],
            total=3,
            limit=10,
            offset=0,
        )
        assert result.items == ["a", "b", "c"]
        assert result.total == 3
        assert result.limit == 10
        assert result.offset == 0

    def test_paginated_empty_items(self) -> None:
        """空列表也应正确序列化。"""
        from app.infra.pagination.schemas import Paginated  # noqa: E402

        result = Paginated[int](items=[], total=0, limit=20, offset=0)
        assert result.items == []
        assert result.total == 0

    def test_paginated_serialization(self) -> None:
        """model_dump 应包含四个字段。"""
        from app.infra.pagination.schemas import Paginated  # noqa: E402

        result = Paginated[str](items=["x"], total=1, limit=10, offset=0)
        d = result.model_dump()
        assert d == {"items": ["x"], "total": 1, "limit": 10, "offset": 0}

    def test_paginated_json_roundtrip(self) -> None:
        """model_dump_json → model_validate_json 往返一致。"""
        from app.infra.pagination.schemas import Paginated  # noqa: E402

        original = Paginated[str](items=["hello"], total=1, limit=20, offset=5)
        json_str = original.model_dump_json()
        restored = Paginated[str].model_validate_json(json_str)
        assert restored.items == original.items
        assert restored.total == original.total
        assert restored.limit == original.limit
        assert restored.offset == original.offset

    def test_thin_subclass_preserves_openapi_title(self) -> None:
        """Thin subclass + model_config title SHALL 保留域 schema 名称。"""
        from app.infra.pagination.schemas import Paginated  # noqa: E402

        class PaginatedProducts(Paginated[str]):
            model_config = ConfigDict(title="PaginatedProducts")

        assert PaginatedProducts.model_config.get("title") == "PaginatedProducts"

        # 实例化应正常工作
        result = PaginatedProducts(items=["p1"], total=1, limit=20, offset=0)
        assert result.items == ["p1"]

    def test_tresponse_is_response_dto_not_orm(self) -> None:
        """TResponse 表示 API Response DTO（Pydantic model），非 ORM 类型。"""
        from pydantic import BaseModel as PydanticBase

        from app.infra.pagination.schemas import Paginated  # noqa: E402

        class FakeProductResponse(PydanticBase):
            id: str
            name: str

        result = Paginated[FakeProductResponse](
            items=[
                FakeProductResponse(id="1", name="Widget"),
                FakeProductResponse(id="2", name="Gadget"),
            ],
            total=2,
            limit=20,
            offset=0,
        )
        assert len(result.items) == 2
        assert result.items[0].name == "Widget"
        assert result.model_dump()["items"][0] == {"id": "1", "name": "Widget"}


# ═══════════════════════════════════════════════════════════════════════
# FastAPI Query 校验（最小 AsyncClient）
# ═══════════════════════════════════════════════════════════════════════


class TestPaginationDependencyQueryValidation:
    """FastAPI Query 校验：200 / 422 边界。"""

    @staticmethod
    def _build_test_app():  # noqa: ANN205
        """构建最小 FastAPI app，仅注册 get_pagination_params 依赖。"""
        from fastapi import Depends, FastAPI

        from app.infra.pagination.deps import get_pagination_params  # noqa: E402
        from app.infra.pagination.schemas import PaginationParams  # noqa: E402

        app = FastAPI()

        @app.get("/test")
        def handler(
            params: PaginationParams = Depends(get_pagination_params),
        ) -> dict[str, int]:
            return {"limit": params.limit, "offset": params.offset}

        return app

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("合法 Query limit=20&offset=0 返回 200")
    async def test_valid_query_returns_200(self) -> None:
        """合法 Query limit=20&offset=0 SHALL 返回 200。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=20&offset=0")
        assert resp.status_code == 200
        assert resp.json() == {"limit": 20, "offset": 0}

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("无 Query 时使用默认 limit=20/offset=0")
    async def test_default_values_applied(self) -> None:
        """无 Query 时 SHALL 使用默认 limit=20 / offset=0。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test")
        assert resp.status_code == 200
        assert resp.json() == {"limit": 20, "offset": 0}

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("limit=101 超过最大值返回 422")
    async def test_limit_exceeds_max_returns_422(self) -> None:
        """limit=101 > MAX_PAGE_LIMIT(100) SHALL 返回 422。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=101&offset=0")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("limit=0 小于最小值返回 422")
    async def test_limit_below_min_returns_422(self) -> None:
        """limit=0 < 1 SHALL 返回 422。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=0&offset=0")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("offset=-1 负数返回 422")
    async def test_offset_negative_returns_422(self) -> None:
        """offset=-1 < 0 SHALL 返回 422。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=20&offset=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("limit=1 返回 200")
    async def test_boundary_limit_1_returns_200(self) -> None:
        """limit=1（最小值）应返回 200。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=1&offset=0")
        assert resp.status_code == 200
        assert resp.json() == {"limit": 1, "offset": 0}

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("limit=100 返回 200")
    async def test_boundary_limit_100_returns_200(self) -> None:
        """limit=100（最大值）应返回 200。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=100&offset=0")
        assert resp.status_code == 200
        assert resp.json() == {"limit": 100, "offset": 0}

    @pytest.mark.asyncio
    @allure.epic("infra")
    @allure.feature("pagination")
    @allure.title("大 offset 正常返回 200")
    async def test_large_offset_returns_200(self) -> None:
        """大 offset 应正常返回 200。"""
        from httpx import ASGITransport, AsyncClient

        app = self._build_test_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test?limit=20&offset=99999")
        assert resp.status_code == 200
        assert resp.json() == {"limit": 20, "offset": 99999}
