"""SAVEPOINT POC: 验证 integration_client + db_session 事务隔离。

场景
----
1. 注册 + 开店 → 独立连接查证数据不可见（自证明，不依赖第二次运行）。
2. migration seed 管理员在 SAVEPOINT 事务内可读（``login_admin`` 应成功返回 token）。

门禁
----
Task 3.0 通过前不得开始 §5 大迁移。本文件作为永久回归测试保留。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.support.helper.auth import login_admin, register_user_via_otp
from tests.support.helper.catalog import create_shop

pytestmark = pytest.mark.integration


class TestSavepointPOC:
    """POC 门禁：SAVEPOINT 事务隔离 + migration seed 可见性。"""

    async def test_register_and_open_shop_in_savepoint(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
        database_url: str,
    ) -> None:
        """注册→开店后，数据仅在外层事务中，库中不可见。

        用独立 Engine（不在 SAVEPOINT 事务内）查询 users/shops 表：
        - 若 SAVEPOINT 失效（数据真提交）→ COUNT > 0 → 断言失败
        - 若 SAVEPOINT 生效 → COUNT == 0 → 断言通过
        """
        fixed_phone = "13900000001"
        fixed_shop = "POC Savepoint Shop"

        # Act: 注册 + 开店（走 SAVEPOINT session）
        registered = await register_user_via_otp(
            integration_client,
            phone=fixed_phone,
        )
        assert registered.status_code == 201
        assert registered.body is not None

        shop = await create_shop(
            integration_client,
            headers={"Authorization": f"Bearer {registered.body.access_token}"},
            name=fixed_shop,
        )
        assert shop.status_code == 201
        assert shop.body is not None

        # Assert: 用独立连接查数据 —— 应不可见
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as conn:
                # users 表
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE phone = :phone"),
                    {"phone": fixed_phone},
                )
                user_count = result.scalar()
                assert user_count == 0, (
                    f"SAVEPOINT 失效：users 表查到 phone={fixed_phone}"
                    f"（count={user_count}，数据泄漏到事务外）"
                )

                # shops 表
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM shops WHERE name = :name"),
                    {"name": fixed_shop},
                )
                shop_count = result.scalar()
                assert shop_count == 0, (
                    f"SAVEPOINT 失效：shops 表查到 {fixed_shop}"
                    f"（count={shop_count}，数据泄漏到事务外）"
                )
        finally:
            await engine.dispose()

    async def test_login_admin_in_savepoint(
        self,
        integration_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """migration seed 管理员在 SAVEPOINT 事务内可读。

        Alembic migration 已 commit 到 MySQL，外层 BEGIN 可见该数据。
        若因事务隔离看不到 → login_admin 返回 401/422。
        """
        logged_in = await login_admin(integration_client)
        assert logged_in.status_code == 200, (
            f"seed 管理员登录失败 (status={logged_in.status_code})"
            " — migration seed 在 SAVEPOINT 事务中不可见"
        )
        assert logged_in.body is not None
        assert logged_in.body.access_token is not None
