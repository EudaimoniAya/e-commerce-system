"""integration 测试用 DB seed（非 HTTP Arrange，走 SAVEPOINT session）。"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_inactive_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> str:
    """向 users 表插入 ``is_active=false`` 用户（需 migration 002），返回 user_id。

    走测试 ``db_session``（SAVEPOINT），teardown 时由外层 ROLLBACK 清除，零残留。
    """
    from pwdlib import PasswordHash

    user_id = str(uuid.uuid4())
    password_hash = PasswordHash.recommended().hash(password)
    await session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, nickname, is_active, created_at, updated_at
            ) VALUES (
                :id, :email, :password_hash, :nickname, 0, NOW(), NOW()
            )
            """
        ),
        {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "nickname": "inactive_user",
        },
    )
    await session.flush()
    return user_id
