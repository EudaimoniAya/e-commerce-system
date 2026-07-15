"""pytest 公共 fixture。"""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# 本地 integration 测试默认连接 test 库（unix socket，与 .env.example 一致）
_DEFAULT_TEST_DATABASE_URL = (
    "mysql+asyncmy://root@localhost/ecommerce_test"
    "?charset=utf8mb4&unix_socket=/tmp/e-commerce-system-mysql.sock"
)

# integration 测试固定 JWT（须 ≥32 字节；与 .env 中 dev 密钥隔离，避免签验不一致）
_DEFAULT_TEST_JWT_SECRET = "test-secret-key-at-least-32-bytes!!"

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"


def _configure_integration_test_env() -> None:
    """注入 integration 测试环境变量（须在 import app 之前调用）。"""
    url = os.environ.get("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
    if "ecommerce_dev" in url:
        url = url.replace("ecommerce_dev", "ecommerce_test")
    os.environ["DATABASE_URL"] = url
    os.environ["APP_ENV"] = "test"
    # 强制覆盖，避免 .env / shell 中 dev JWT 与测试签发密钥不一致导致 401
    os.environ["JWT_SECRET_KEY"] = _DEFAULT_TEST_JWT_SECRET


def _reset_settings_cache() -> None:
    """清除 Settings 单例缓存，使后续 get_settings() 读取最新环境变量。"""
    from app.infra.config import get_settings

    get_settings.cache_clear()


# import app 前配置 env 并清缓存，避免 get_settings() 缓存 .env 中的 dev 配置
_configure_integration_test_env()
_reset_settings_cache()

from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _integration_test_database_url() -> None:
    """session 级再次确保测试 env 与 Settings 缓存一致。"""
    _configure_integration_test_env()
    _reset_settings_cache()


@pytest.fixture(scope="session")
def database_url() -> str:
    """当前测试会话使用的 MySQL 连接串（指向 ecommerce_test）。"""
    return os.environ["DATABASE_URL"]


@pytest.fixture(autouse=True)
async def _reset_global_database_engine(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """integration 测试前后重置全局 engine，避免跨事件循环复用连接池。"""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    _reset_settings_cache()
    from app.infra.database import reset_engine

    await reset_engine()
    yield
    await reset_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient，与 pytest-asyncio 共用同一事件循环。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """每个测试在独立事务内执行，结束后 rollback 保证零副作用。"""
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


# --- auth integration 测试 helper ---


def unique_email(prefix: str = "user") -> str:
    """生成唯一测试邮箱，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> dict[str, Any]:
    """调用 POST /auth/register，返回响应与请求上下文。"""
    payload: dict[str, str] = {
        "email": email or unique_email(),
        "password": password,
    }
    if nickname is not None:
        payload["nickname"] = nickname

    response = await client.post("/auth/register", json=payload)
    body: Any | None
    if response.content:
        body = response.json()
    else:
        body = None

    return {
        "response": response,
        "status_code": response.status_code,
        "json": body,
        "email": payload["email"],
        "password": password,
    }


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> dict[str, Any]:
    """调用 POST /auth/login，返回响应与请求上下文。"""
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    body: Any | None
    if response.content:
        body = response.json()
    else:
        body = None

    return {
        "response": response,
        "status_code": response.status_code,
        "json": body,
        "email": email,
        "password": password,
    }


@pytest.fixture
async def authenticated_user(client: AsyncClient) -> dict[str, Any]:
    """注册成功并返回 access_token 与 Bearer 请求头（供 /users/me 等已认证端点）。"""
    registered = await register_user(client)
    if registered["status_code"] != 201 or not registered["json"]:
        return {
            **registered,
            "access_token": None,
            "headers": {},
        }

    access_token = registered["json"]["access_token"]
    return {
        **registered,
        "access_token": access_token,
        "headers": auth_headers(access_token),
        "user": registered["json"].get("user"),
    }


# --- catalog shop integration 测试 helper ---


def unique_shop_name(prefix: str = "shop") -> str:
    """生成唯一店名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def create_shop_payload(
    *,
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> dict[str, str]:
    """构造 POST /shops 请求体。"""
    payload: dict[str, str] = {"name": name or unique_shop_name()}
    if description is not None:
        payload["description"] = description
    if logo_url is not None:
        payload["logo_url"] = logo_url
    return payload


async def register_and_open_shop(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    shop_name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> dict[str, Any]:
    """注册用户并调用 POST /shops，返回注册与开店上下文。"""
    registered = await register_user(client, email=email, password=password)
    if registered["status_code"] != 201 or not registered["json"]:
        return {
            **registered,
            "access_token": None,
            "headers": {},
            "shop_payload": create_shop_payload(name=shop_name),
            "register": registered,
        }

    access_token = registered["json"]["access_token"]
    headers = auth_headers(access_token)
    shop_payload = create_shop_payload(
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )
    shop_response = await client.post("/shops", json=shop_payload, headers=headers)
    shop_body: Any | None
    if shop_response.content:
        shop_body = shop_response.json()
    else:
        shop_body = None

    return {
        "response": shop_response,
        "status_code": shop_response.status_code,
        "json": shop_body,
        "email": registered["email"],
        "password": registered["password"],
        "access_token": access_token,
        "headers": headers,
        "user": registered["json"].get("user"),
        "shop_payload": shop_payload,
        "register": registered,
    }


@pytest.fixture
async def shop_owner(client: AsyncClient) -> dict[str, Any]:
    """注册并开店成功，返回 token、headers 与店铺资料（供 catalog integration 测试）。"""
    return await register_and_open_shop(client)


# --- catalog category/product integration 测试 helper ---

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PASSWORD = "1919810810"


def unique_category_name(prefix: str = "cat") -> str:
    """生成唯一类目名，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def admin_auth_headers(client: AsyncClient) -> dict[str, Any]:
    """seed 管理员登录，返回 token 与 Bearer 请求头（供 POST /categories 等 admin 端点）。"""
    logged_in = await login_user(
        client,
        email=_ADMIN_SEED_EMAIL,
        password=_ADMIN_SEED_PASSWORD,
    )
    if logged_in["status_code"] != 200 or not logged_in["json"]:
        pytest.fail(
            f"seed 管理员登录失败（status={logged_in['status_code']}），"
            "请确认 ecommerce_test 已 migrate 且 seed admin 存在"
        )

    access_token = logged_in["json"]["access_token"]
    if not access_token:
        pytest.fail("seed 管理员登录响应缺少 access_token")

    return {
        **logged_in,
        "access_token": access_token,
        "headers": auth_headers(access_token),
    }


async def create_category(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """调用 POST /categories，返回响应与请求上下文。"""
    payload: dict[str, str] = {"name": name or unique_category_name()}
    if parent_id is not None:
        payload["parent_id"] = parent_id

    response = await client.post("/categories", json=payload, headers=headers)
    body: Any | None
    if response.content:
        body = response.json()
    else:
        body = None

    return {
        "response": response,
        "status_code": response.status_code,
        "json": body,
        "payload": payload,
    }


@pytest.fixture
def product_payload() -> Any:
    """返回构造 POST /products 请求体的工厂函数（需传入 category_ids 与 primary_category_id）。"""

    def _product_payload(
        *,
        name: str | None = None,
        price: str = "99.00",
        stock: int = 10,
        description: str | None = None,
        image_url: str | None = None,
        is_published: bool = False,
        category_ids: list[str],
        primary_category_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name or f"product-{uuid.uuid4().hex[:12]}",
            "price": price,
            "stock": stock,
            "is_published": is_published,
            "category_ids": category_ids,
            "primary_category_id": primary_category_id,
        }
        if description is not None:
            payload["description"] = description
        if image_url is not None:
            payload["image_url"] = image_url
        return payload

    return _product_payload
