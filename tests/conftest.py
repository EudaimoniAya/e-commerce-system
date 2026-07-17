"""pytest 公共 fixture。"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.catalog.schemas import CategoryResponse, ShopResponse
from app.user.schemas import TokenResponse
from tests.support.builders import (
    build_category_create,
    build_login_request,
    build_register_request,
    build_shop_create,
    unique_category_name,
    unique_email,
    unique_shop_name,
)
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.results import (
    CategoryResult,
    LoginResult,
    RegisterResult,
    ShopResult,
)

# 公开 re-export（含 unique_*，供测试模块 `from tests.conftest import ...`）
__all__ = [
    "AdminAuthContext",
    "AuthContext",
    "CategoryResult",
    "LoginResult",
    "RegisterResult",
    "ShopOwnerContext",
    "ShopResult",
    "admin_auth_headers",
    "auth_headers",
    "authenticated_user",
    "client",
    "create_category",
    "create_shop",
    "database_url",
    "db_session",
    "login_user",
    "register_and_open_shop",
    "register_user",
    "shop_owner",
    "unique_category_name",
    "unique_email",
    "unique_shop_name",
]

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


def _ensure_integration_auth_env() -> None:
    """每次签发/校验 JWT 前确保测试 env 与 Settings 缓存一致。"""
    _configure_integration_test_env()
    _reset_settings_cache()


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

    _ensure_integration_auth_env()
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


def _auth_context_from_register(registered: RegisterResult) -> AuthContext:
    """由 RegisterResult 构造 AuthContext。"""
    if registered.status_code != 201 or registered.body is None:
        return AuthContext(
            status_code=registered.status_code,
            body=registered.body,
            email=registered.email,
            password=registered.password,
            access_token=None,
            headers={},
            user=None,
        )

    access_token = registered.body.access_token
    return AuthContext(
        status_code=registered.status_code,
        body=registered.body,
        email=registered.email,
        password=registered.password,
        access_token=access_token,
        headers=auth_headers(access_token),
        user=registered.body.user,
    )


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> RegisterResult:
    """调用 POST /auth/register，返回 RegisterResult。"""
    _ensure_integration_auth_env()
    request = build_register_request(
        email=email,
        password=password,
        nickname=nickname,
    )
    response = await client.post(
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
    _ensure_integration_auth_env()
    request = build_login_request(email=email, password=password)
    response = await client.post(
        "/auth/login",
        json=request.model_dump(mode="json"),
    )
    return LoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


@pytest.fixture
async def authenticated_user(client: AsyncClient) -> AuthContext:
    """注册成功并返回 access_token 与 Bearer 请求头（供 /users/me 等已认证端点）。"""
    _ensure_integration_auth_env()
    registered = await register_user(client)
    return _auth_context_from_register(registered)


# --- catalog shop integration 测试 helper ---


async def create_shop(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    description: str | None = None,
    logo_url: str | None = None,
) -> ShopResult:
    """调用 POST /shops，返回 ShopResult。"""
    _ensure_integration_auth_env()
    request = build_shop_create(
        name=name,
        description=description,
        logo_url=logo_url,
    )
    response = await client.post(
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
) -> ShopOwnerContext:
    """注册用户并调用 POST /shops，返回 ShopOwnerContext。"""
    _ensure_integration_auth_env()
    registered = await register_user(client, email=email, password=password)
    auth = _auth_context_from_register(registered)
    shop_request = build_shop_create(
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )

    if registered.status_code != 201 or registered.body is None:
        # 注册未完整成功时不得沿用 201，避免后续用空 headers 触发 401
        failed_status = registered.status_code if registered.status_code != 201 else 0
        return ShopOwnerContext(
            status_code=failed_status,
            body=None,
            auth=auth,
            shop=None,
            shop_request=shop_request,
            headers={},
            email=registered.email,
            password=registered.password,
        )

    _ensure_integration_auth_env()
    shop_result = await create_shop(
        client,
        headers=auth.headers,
        name=shop_name,
        description=description,
        logo_url=logo_url,
    )
    return ShopOwnerContext(
        status_code=shop_result.status_code,
        body=shop_result.body,
        auth=auth,
        shop=shop_result.body,
        shop_request=shop_result.request,
        headers=auth.headers,
        email=registered.email,
        password=registered.password,
    )


@pytest.fixture
async def shop_owner(client: AsyncClient) -> ShopOwnerContext:
    """注册并开店成功，返回 token、headers 与店铺资料（供 catalog integration 测试）。"""
    return await register_and_open_shop(client)


# --- catalog category/product integration 测试 helper ---

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PASSWORD = "1919810810"


@pytest.fixture
async def admin_auth_headers(client: AsyncClient) -> AdminAuthContext:
    """seed 管理员登录，返回 token 与 Bearer 请求头（供 POST /categories 等 admin 端点）。"""
    _ensure_integration_auth_env()
    logged_in = await login_user(
        client,
        email=_ADMIN_SEED_EMAIL,
        password=_ADMIN_SEED_PASSWORD,
    )
    if logged_in.status_code != 200 or logged_in.body is None:
        pytest.fail(
            f"seed 管理员登录失败（status={logged_in.status_code}），"
            "请确认 ecommerce_test 已 migrate 且 seed admin 存在"
        )

    access_token = logged_in.body.access_token
    if not access_token:
        pytest.fail("seed 管理员登录响应缺少 access_token")

    return AdminAuthContext(
        status_code=logged_in.status_code,
        body=logged_in.body,
        email=logged_in.email,
        password=logged_in.password,
        access_token=access_token,
        headers=auth_headers(access_token),
    )


async def create_category(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    parent_id: str | None = None,
) -> CategoryResult:
    """调用 POST /categories，返回 CategoryResult。"""
    _ensure_integration_auth_env()
    request = build_category_create(name=name, parent_id=parent_id)
    response = await client.post(
        "/categories",
        json=request.model_dump(mode="json"),
        headers=headers,
    )
    return CategoryResult(
        status_code=response.status_code,
        body=_parse_category_body(response),
        request=request,
    )
