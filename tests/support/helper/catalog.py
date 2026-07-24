"""catalog 域 HTTP helper。"""

import uuid
from decimal import Decimal

from httpx import AsyncClient, Response

from app.catalog.schemas import CategoryResponse, ProductResponse, ShopResponse
from tests.support.helper.auth import register_user
from tests.support.builders import build_category_create, build_product_create, build_shop_create
from tests.support.utils import bearer_headers
from tests.support.results import CategoryResult, ProductResult, RegisterResult, ShopResult


def _parse_shop_body(response: Response) -> ShopResponse | None:
    """2xx 时解析 ShopResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return ShopResponse.model_validate(response.json())
    return None


def _parse_category_body(response: Response) -> CategoryResponse | None:
    """2xx 时解析 CategoryResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return CategoryResponse.model_validate(response.json())
    return None


def _parse_product_body(response: Response) -> ProductResponse | None:
    """2xx 时解析 ProductResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return ProductResponse.model_validate(response.json())
    return None


async def create_shop(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> ShopResult:
    """调用 POST /shops，返回 ShopResult。"""
    request = build_shop_create(
        name=name,
        description=description,
        logo_url=logo_url,
    )
    response: Response = await client.post(
        "/shops",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return ShopResult(
        status_code=response.status_code,
        body=_parse_shop_body(response),
        request=request,
    )


async def register_and_open_shop(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "password123",
    shop_name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> tuple[RegisterResult, ShopResult | None]:
    """注册用户并调用 POST /shops，返回 ``(RegisterResult, ShopResult)``。

    注册失败或开店失败时 ShopResult 为 None。
    """
    registered: RegisterResult = await register_user(
        client, email=email, password=password
    )

    if registered.status_code != 201 or registered.body is None:
        return (registered, None)

    shop_result: ShopResult = await create_shop(
        client,
        headers=bearer_headers(registered.body.access_token),
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )
    return (registered, shop_result)


async def create_category(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    parent_id: str | None = None,
) -> CategoryResult:
    """调用 POST /categories，返回 CategoryResult。"""
    request = build_category_create(name=name, parent_id=parent_id)
    response: Response = await client.post(
        "/categories",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return CategoryResult(
        status_code=response.status_code,
        body=_parse_category_body(response),
        request=request,
    )


async def create_product(
    client: AsyncClient,
    *,
    shop_owner_token: str,
    category: CategoryResult,
    name: str | None = None,
    price: str | Decimal = "99.00",
    stock: int = 10,
    description: str | None = None,
    image_url: str | None = None,
    is_published: bool = False,
) -> ProductResult:
    """调用 POST /products，返回 ProductResult（不 assert 成功状态码）。

    扇入前置 ``shop_owner_token`` / ``category`` 须由 Case 或 fixture 持有；
    ``category.body`` 为 None 时使用占位 UUID，由 API 如实返回错误。
    """
    category_id = (
        category.body.id if category.body is not None else str(uuid.uuid4())
    )
    request = build_product_create(
        name=name,
        price=price,
        stock=stock,
        description=description,
        image_url=image_url,
        is_published=is_published,
        category_ids=[category_id],
        primary_category_id=category_id,
    )
    response: Response = await client.post(
        "/products",
        json=request.model_dump(mode="json"),
        headers=bearer_headers(shop_owner_token),
    )
    return ProductResult(
        status_code=response.status_code,
        body=_parse_product_body(response),
        request=request,
    )
