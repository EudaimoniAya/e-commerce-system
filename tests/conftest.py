"""pytest 公共 fixture 与 support 符号 re-export。"""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.support.builders import (
    unique_category_name,
    unique_email,
    unique_shop_name,
)
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.env import bootstrap_test_env
from tests.support.helpers import (
    auth_headers,
    create_category,
    create_product,
    create_shop,
    ensure_integration_auth_env,
    login_admin,
    login_user,
    register_and_open_shop,
    register_authenticated,
    register_user,
)
from tests.support.results import (
    CategoryResult,
    LoginResult,
    ProductResult,
    RegisterResult,
    ShopResult,
)

# 公开 re-export（fixture + support 符号；Case 亦可直接 from tests.support.*）
__all__ = [
    "AdminAuthContext",
    "AuthContext",
    "CategoryResult",
    "LoginResult",
    "ProductResult",
    "RegisterResult",
    "ShopOwnerContext",
    "ShopResult",
    "admin_auth_headers",
    "auth_headers",
    "authenticated_user",
    "client",
    "create_category",
    "integration_client",
    "create_product",
    "create_shop",
    "database_url",
    "db_session",
    "login_admin",
    "login_user",
    "register_and_open_shop",
    "register_authenticated",
    "register_user",
    "shop_owner",
    "unique_category_name",
    "unique_email",
    "unique_shop_name",
]

# import app 前 bootstrap 测试环境：确保 Settings 从 .env.test 加载
bootstrap_test_env()

from app.main import app  # noqa: E402


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

    ensure_integration_auth_env()
    from app.infra.database import reset_engine

    await reset_engine()
    yield
    await reset_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient，与 pytest-asyncio 共用同一事件循环。

    无 ``get_db`` override，适合 health 等不需写库的探针测试。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def integration_client(
    db_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient，依赖 ``db_session`` 提供 ``get_db`` override。

    所有 HTTP 请求走 SAVEPOINT 测试 session，与 ``db_session`` 同一事务。
    写入的数据在测试结束后由外层 ROLLBACK 清除，零残留。
    适合 ``@pytest.mark.integration`` 业务 HTTP 用例。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """SAVEPOINT 事务隔离的 AsyncSession，经 dependency_overrides 使 HTTP 共用同一 session。

    - ``join_transaction_mode='create_savepoint'``：service 内 ``session.commit()`` 仅提交
      SAVEPOINT，不提交外层事务。
    - 注册 ``app.dependency_overrides[get_db]`` → HTTP 请求走测试 session。
    - Teardown：pop override → rollback 外层事务 → 零数据残留。
    - 保留 expire_on_commit=False 避免提交 SAVEPOINT 后 ORM 实例过期。
    """
    from app.infra.database import get_db
    from app.main import app

    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        async def _override_get_db() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await trans.rollback()
    await engine.dispose()


@pytest.fixture
async def authenticated_user(client: AsyncClient) -> AuthContext:
    """注册成功后的极薄 AuthContext（orchestrator → fail-fast → Context）。"""
    root = await register_authenticated(client)
    registered = root.step(RegisterResult)
    if registered.status_code != 201 or registered.body is None:
        pytest.fail(
            f"注册 Setup 失败（status={registered.status_code}），"
            "authenticated_user fixture 要求注册成功"
        )
    return AuthContext(root=root)


@pytest.fixture
async def shop_owner(client: AsyncClient) -> ShopOwnerContext:
    """注册并开店成功后的极薄 ShopOwnerContext（orchestrator → fail-fast → Context）。"""
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
    """seed 管理员登录后的极薄 AdminAuthContext（orchestrator → fail-fast → Context）。"""
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
