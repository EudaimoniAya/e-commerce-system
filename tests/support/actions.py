"""integration 测试 HTTP helper 与 orchestrator。"""

import os
import uuid
from decimal import Decimal

from httpx import AsyncClient, Response

from app.catalog.schemas import CategoryResponse, ProductResponse, ShopResponse
from app.user.schemas import TokenResponse
from tests.support.builders import (
    build_category_create,
    build_login_request,
    build_product_create,
    build_register_request,
    build_shop_create,
)
from tests.support.pipeline import PipelineResult
from tests.support.projections import bearer_headers
from tests.support.results import (
    CategoryResult,
    LoginResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)

# 本地 integration 测试默认连接 test 库（unix socket，与 .env.example 一致）
_DEFAULT_TEST_DATABASE_URL = (
    "mysql+asyncmy://root@localhost/ecommerce_test"
    "?charset=utf8mb4&unix_socket=/tmp/e-commerce-system-mysql.sock"
)

# integration 测试固定 JWT（须 ≥32 字节；与 .env 中 dev 密钥隔离，避免签验不一致）
_DEFAULT_TEST_JWT_SECRET = "test-secret-key-at-least-32-bytes!!"

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PASSWORD = "1919810810"


def configure_integration_test_env() -> None:
    """注入 integration 测试环境变量（须在 import app 之前调用）。"""
    url = os.environ.get("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
    if "ecommerce_dev" in url:
        url = url.replace("ecommerce_dev", "ecommerce_test")
    os.environ["DATABASE_URL"] = url
    os.environ["APP_ENV"] = "test"
    # 强制覆盖，避免 .env / shell 中 dev JWT 与测试签发密钥不一致导致 401
    os.environ["JWT_SECRET_KEY"] = _DEFAULT_TEST_JWT_SECRET


def reset_settings_cache() -> None:
    """清除 Settings 单例缓存，使后续 get_settings() 读取最新环境变量。"""
    from app.infra.config import get_settings

    get_settings.cache_clear()


def ensure_integration_auth_env() -> None:
    """每次签发/校验 JWT 前确保测试 env 与 Settings 缓存一致。"""
    configure_integration_test_env()
    reset_settings_cache()


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


def _parse_token_body(response: Response) -> TokenResponse | None:
    """2xx 时解析 TokenResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return TokenResponse.model_validate(response.json())
    return None


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


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> RegisterResult:
    """调用 POST /auth/register，返回 RegisterResult。"""
    ensure_integration_auth_env()
    request = build_register_request(
        email=email,
        password=password,
        nickname=nickname,
    )
    response: Response = await client.post(
        "/auth/register",
        json=request.model_dump(mode="json"),
    )
    return RegisterResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginResult:
    """调用 POST /auth/login，返回 LoginResult。"""
    ensure_integration_auth_env()
    request = build_login_request(email=email, password=password)
    response: Response = await client.post(
        "/auth/login",
        json=request.model_dump(mode="json"),
    )
    return LoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_admin(client: AsyncClient) -> PipelineResult:
    """使用 migration seed 管理员登录，返回 ``PipelineResult(steps=(LoginResult,))``。"""
    logged_in = await login_user(
        client,
        email=_ADMIN_SEED_EMAIL,
        password=_ADMIN_SEED_PASSWORD,
    )
    return PipelineResult(steps=(logged_in,))


async def create_shop(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> ShopResult:
    """调用 POST /shops，返回 ShopResult。"""
    ensure_integration_auth_env()
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
    password: str = _DEFAULT_TEST_PASSWORD,
    shop_name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> PipelineResult:
    """注册用户并调用 POST /shops，返回 ``PipelineResult``。

    注册失败时 steps 仅含 ``RegisterResult``；成功开店后为
    ``(RegisterResult, ShopResult)``。
    """
    ensure_integration_auth_env()
    registered: RegisterResult = await register_user(
        client, email=email, password=password
    )

    if registered.status_code != 201 or registered.body is None:
        return PipelineResult(steps=(registered,))

    ensure_integration_auth_env()
    shop_result: ShopResult = await create_shop(
        client,
        headers=bearer_headers(registered),
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )
    return PipelineResult(steps=(registered, shop_result))


async def create_category(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    parent_id: str | None = None,
) -> CategoryResult:
    """调用 POST /categories，返回 CategoryResult。"""
    ensure_integration_auth_env()
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
    shop_owner: PipelineResult,
    category: CategoryResult,
    name: str | None = None,
    price: str | Decimal = "99.00",
    stock: int = 10,
    description: str | None = None,
    image_url: str | None = None,
    is_published: bool = False,
) -> ProductResult:
    """调用 POST /products，返回 ProductResult（不 assert 成功状态码）。

    扇入前置 ``shop_owner`` / ``category`` 须由 Case 或 fixture 持有；
    ``category.body`` 为 None 时使用占位 UUID，由 API 如实返回错误。
    """
    ensure_integration_auth_env()
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
        headers=bearer_headers(shop_owner.step(RegisterResult)),
    )
    return ProductResult(
        status_code=response.status_code,
        body=_parse_product_body(response),
        request=request,
    )
