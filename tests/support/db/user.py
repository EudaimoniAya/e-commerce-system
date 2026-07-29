"""user 域 DB seed/断言 helper（使用与 override 相同的 AsyncSession）。"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_active_user(
    session: AsyncSession,
    *,
    email: str | None = None,
    phone: str | None = None,
    nickname: str = "test-user",
    password_hash: str = "dummyhash",
) -> str:
    """向 users 表插入 ``is_active=true`` 用户，返回 user_id。

    ``email`` 和 ``phone`` 均为可选；至少提供一个方可满足 NOT NULL / UNIQUE 约束。
    """
    _email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, nickname, is_active,
                phone, created_at, updated_at
            ) VALUES (
                :id, :email, :password_hash, :nickname, 1,
                :phone, NOW(), NOW()
            )
            """
        ),
        {
            "id": user_id,
            "email": _email,
            "password_hash": password_hash,
            "nickname": nickname,
            "phone": phone,
        },
    )
    await session.flush()
    return user_id


async def seed_inactive_user(
    session: AsyncSession,
    email: str | None = None,
    password: str = "password123",
    phone: str | None = None,
) -> str:
    """向 users 表插入 ``is_active=false`` 用户，返回 user_id。

    走测试 ``db_session``（SAVEPOINT），teardown 时由外层 ROLLBACK 清除，零残留。
    """
    from pwdlib import PasswordHash

    _email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    user_id = str(uuid.uuid4())
    password_hash = PasswordHash.recommended().hash(password)
    await session.execute(
        text(
            """
            INSERT INTO users (
                id, email, password_hash, nickname, is_active,
                phone, created_at, updated_at
            ) VALUES (
                :id, :email, :password_hash, :nickname, 0,
                :phone, NOW(), NOW()
            )
            """
        ),
        {
            "id": user_id,
            "email": _email,
            "password_hash": password_hash,
            "nickname": "inactive_user",
            "phone": phone,
        },
    )
    await session.flush()
    return user_id
