"""pytest 公共 fixture。"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.support.actions import (
    auth_headers,
    configure_integration_test_env,
    create_category,
    create_product,
    create_shop,
    ensure_integration_auth_env,
    login_admin,
    login_user,
    register_and_open_shop,
    register_user,
    reset_settings_cache,
)
from tests.support.builders import (
    unique_category_name,
    unique_email,
    unique_shop_name,
)
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.pipeline import PipelineResult
from tests.support.results import (
    CategoryResult,
    LoginResult,
    RegisterResult,
    ShopResult,
)

# 兼容 infra 等仍从 conftest 引用私有名的测试
_configure_integration_test_env = configure_integration_test_env
_reset_settings_cache = reset_settings_cache
_ensure_integration_auth_env = ensure_integration_auth_env

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
    "create_product",
    "create_shop",
    "database_url",
    "db_session",
    "login_admin",
    "login_user",
    "register_and_open_shop",
    "register_user",
    "shop_owner",
    "unique_category_name",
    "unique_email",
    "unique_shop_name",
]

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


@pytest.fixture
async def authenticated_user(client: AsyncClient) -> AuthContext:
    """注册成功后的极薄 AuthContext（供 /users/me 等已认证端点）。"""
    _ensure_integration_auth_env()
    registered: RegisterResult = await register_user(client)
    if registered.status_code != 201 or registered.body is None:
        pytest.fail(
            f"注册 Setup 失败（status={registered.status_code}），"
            "authenticated_user fixture 要求注册成功"
        )
    return AuthContext(root=PipelineResult(steps=(registered,)))


@pytest.fixture
async def shop_owner(client: AsyncClient) -> ShopOwnerContext:
    """注册并开店成功后的极薄 ShopOwnerContext（供 catalog integration 测试）。"""
    root = await register_and_open_shop(client)
    try:
        shop = root.step(ShopResult)
    except LookupError:
        reg = root.step(RegisterResult)
        pytest.fail(
            f"开店 Setup 未产生 ShopResult（register status={reg.status_code}）"
        )
    if shop.status_code != 201 or shop.body is None:
        pytest.fail(
            f"开店 Setup 失败（status={shop.status_code}），"
            "shop_owner fixture 要求开店成功"
        )
    return ShopOwnerContext(root=root)


@pytest.fixture
async def admin_auth_headers(client: AsyncClient) -> AdminAuthContext:
    """seed 管理员登录后的极薄 AdminAuthContext（供 POST /categories 等 admin 端点）。"""
    root = await login_admin(client)
    logged_in = root.step(LoginResult)
    if logged_in.status_code != 200 or logged_in.body is None:
        pytest.fail(
            f"seed 管理员登录失败（status={logged_in.status_code}），"
            "请确认 ecommerce_test 已 migrate 且 seed admin 存在"
        )

    if not logged_in.body.access_token:
        pytest.fail("seed 管理员登录响应缺少 access_token")

    return AdminAuthContext(root=root)
