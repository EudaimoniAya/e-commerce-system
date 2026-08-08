"""pytest 公共 fixture 与 support 符号 re-export。"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.support.builders import (
    unique_category_name,
    unique_email,
    unique_phone,
    unique_shop_name,
)
from tests.support.contexts import AdminAuthContext, AuthContext, ShopOwnerContext
from tests.support.helper.auth import (
    _ADMIN_SEED_PASSWORD,
    _ADMIN_SEED_PHONE,
    auth_headers,
    login_user,
    register_user_via_otp,
)
from tests.support.helper.catalog import (
    create_category,
    create_product,
    create_shop,
)
from tests.support.results import (
    BatchDeleteFavoritesResult,
    BatchPayResult,
    CartItemResult,
    CartListResult,
    CategoryResult,
    CheckoutBatchResult,
    CheckoutResult,
    FavoriteListResult,
    FavoriteResult,
    LoginResult,
    MediaResult,
    ProductResult,
    ShopResult,
    SmsLoginResult,
    SmsRegisterResult,
    SmsSendResult,
)
from tests.support.utils import bootstrap_test_env

# 公开 re-export（fixture + support 符号；Case 亦可直接 from tests.support.*）
__all__ = [
    "AdminAuthContext",
    "AuthContext",
    "BatchDeleteFavoritesResult",
    "BatchPayResult",
    "CartItemResult",
    "CartListResult",
    "CategoryResult",
    "CheckoutBatchResult",
    "CheckoutResult",
    "FavoriteListResult",
    "FavoriteResult",
    "LoginResult",
    "MediaResult",
    "ProductResult",
    "ShopOwnerContext",
    "ShopResult",
    "SmsLoginResult",
    "SmsRegisterResult",
    "SmsSendResult",
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
    "login_user",
    "register_user_via_otp",
    "second_shop_owner",
    "shop_owner",
    "unique_category_name",
    "unique_email",
    "unique_phone",
    "unique_shop_name",
]

# import app 前 bootstrap 测试环境：确保 Settings 从 .env.test 加载
bootstrap_test_env()

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def database_url() -> str:
    """当前测试会话使用的 MySQL 连接串（指向 ecommerce_test，从 Settings 读取）。"""
    from app.infra.config import get_settings

    return get_settings().database_url


@pytest.fixture(autouse=True)
async def _reset_global_database_engine(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """integration 测试前后重置全局 engine，避免跨事件循环复用连接池。"""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    from app.infra.database import reset_engine

    await reset_engine()
    yield
    await reset_engine()


@pytest.fixture(autouse=True)
async def _reset_global_redis(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """integration 测试前后重置全局 Redis 连接，避免跨事件循环复用连接池。"""
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    from app.infra.redis import reset_redis

    await reset_redis()
    yield
    await reset_redis()


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
    flush_test_redis_db: None,
) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient，依赖 ``db_session`` 提供 ``get_db`` override。

    所有 HTTP 请求走 SAVEPOINT 测试 session，与 ``db_session`` 同一事务。
    写入的数据在测试结束后由外层 ROLLBACK 清除，零残留。
    适合 ``@pytest.mark.integration`` 业务 HTTP 用例。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _override_media_storage_backend(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """integration 测试自动注入 InMemoryBackend，避免文件 IO 残留。

    仅 ``@pytest.mark.integration`` 测例触发；单元测试不受影响。
    ``app/media/`` 模块创建后自动激活；当前不存在则静默跳过。
    """
    if request.node.get_closest_marker("integration") is None:
        yield
        return

    try:
        from app.media.deps import get_storage_backend  # noqa: F401
        from app.media.storage.memory import InMemoryBackend  # noqa: F401
    except ImportError:
        yield
        return

    from app.main import app as _app

    backend = InMemoryBackend()
    _app.dependency_overrides[get_storage_backend] = lambda: backend
    try:
        yield
    finally:
        _app.dependency_overrides.pop(get_storage_backend, None)


@pytest.fixture
async def authenticated_user(integration_client: AsyncClient) -> AuthContext:
    """注册成功后的极薄 AuthContext（orchestrator → fail-fast → Context）。"""
    registered = await register_user_via_otp(integration_client)
    if registered.status_code != 201 or registered.body is None:
        pytest.fail(
            f"注册 Setup 失败（status={registered.status_code}），"
            "authenticated_user fixture 要求注册成功"
        )
    return AuthContext(
        access_token=registered.body.access_token,
        phone=registered.phone,
    )


@pytest.fixture
async def shop_owner(integration_client: AsyncClient) -> ShopOwnerContext:
    """注册并开店成功后的极薄 ShopOwnerContext（orchestrator → fail-fast → Context）。"""
    registered = await register_user_via_otp(integration_client)
    if registered.status_code != 201 or registered.body is None:
        pytest.fail(
            f"注册 Setup 失败（status={registered.status_code}），"
            "shop_owner fixture 要求注册成功"
        )

    shop_result = await create_shop(
        integration_client,
        headers=auth_headers(registered.body.access_token),
    )
    if shop_result.status_code != 201 or shop_result.body is None:
        pytest.fail(
            f"开店 Setup 失败（status={shop_result.status_code}），"
            "shop_owner fixture 要求开店成功"
        )

    return ShopOwnerContext(
        access_token=registered.body.access_token,
        shop_id=shop_result.body.id,
        phone=registered.phone,
    )


@pytest.fixture
async def second_shop_owner(integration_client: AsyncClient) -> ShopOwnerContext:
    """注册第二个用户并开店（与 ``shop_owner`` 独立，用于跨店场景）。

    与 ``shop_owner`` 逻辑完全相同，仅身份独立。
    """
    registered = await register_user_via_otp(integration_client)
    if registered.status_code != 201 or registered.body is None:
        pytest.fail(
            f"注册 Setup 失败（status={registered.status_code}），"
            "second_shop_owner fixture 要求注册成功"
        )

    shop_result = await create_shop(
        integration_client,
        headers=auth_headers(registered.body.access_token),
    )
    if shop_result.status_code != 201 or shop_result.body is None:
        pytest.fail(
            f"开店 Setup 失败（status={shop_result.status_code}），"
            "second_shop_owner fixture 要求开店成功"
        )

    return ShopOwnerContext(
        access_token=registered.body.access_token,
        shop_id=shop_result.body.id,
        phone=registered.phone,
    )


@pytest.fixture
async def admin_auth_headers(integration_client: AsyncClient) -> AdminAuthContext:
    """seed 管理员登录后的极薄 AdminAuthContext（orchestrator → fail-fast → Context）。"""
    logged_in = await login_user(
        integration_client,
        identifier=_ADMIN_SEED_PHONE,
        password=_ADMIN_SEED_PASSWORD,
    )
    if logged_in.status_code != 200 or logged_in.body is None:
        pytest.fail(
            f"seed 管理员登录失败（status={logged_in.status_code}），"
            "请确认 ecommerce_test 已 migrate 且 seed admin 存在"
        )

    if not logged_in.body.access_token:
        pytest.fail("seed 管理员登录响应缺少 access_token")

    return AdminAuthContext(access_token=logged_in.body.access_token)


# ── Redis fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def redis_url() -> str:
    """当前测试会话使用的 Redis 连接串（指向 /1，从 Settings 读取）。"""
    from app.infra.config import get_settings

    return get_settings().redis_url


@pytest.fixture(scope="session")
def _redis_url(redis_url: str) -> str:
    """确保 Settings 已加载 test Redis URL（供 redis_client 依赖）。"""
    return redis_url


@pytest.fixture
async def redis_client(_redis_url: str) -> AsyncIterator[Redis]:
    """Async Redis client，经 infra get_redis() 获取（连接池复用）。

    写 key 的用例请同时依赖 ``flush_test_redis_db`` 以隔离残留。
    """
    from app.infra.redis import get_redis

    client = get_redis()
    yield client
    # 不 close——连接池由 infra 模块级管理，复用连接


@pytest.fixture
async def flush_test_redis_db(redis_client: Redis) -> None:
    """对当前逻辑库执行 FLUSHDB，确保 test 用例之间 key 无残留。

    禁止 FLUSHALL：它清空所有 db（含 dev /0），无视逻辑库隔离。
    """
    await redis_client.flushdb()
