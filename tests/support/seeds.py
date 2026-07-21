"""integration 测试用 DB seed（非 HTTP Arrange）。"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def seed_inactive_user(database_url: str, email: str, password: str) -> str:
    """向 users 表插入 ``is_active=false`` 用户（需 migration 002），返回 user_id。"""
    from pwdlib import PasswordHash

    user_id = str(uuid.uuid4())
    password_hash = PasswordHash.recommended().hash(password)
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.execute(
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
    await engine.dispose()
    return user_id
