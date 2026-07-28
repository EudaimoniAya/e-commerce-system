"""migration 003 seed 管理员 integration 测试（TDD 红阶段）。"""

import os
import subprocess
import sys

import allure
import pytest
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# migration seed 管理员邮箱（见 design.md）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
# migration 内使用的明文密码（仅测试断言 pwdlib 哈希，非 API 暴露）
_ADMIN_SEED_PLAINTEXT_PASSWORD = "1919810810"

_hasher = PasswordHash.recommended()


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("admin_seed")
@allure.title("upgrade head 后存在 is_admin=true 的 seed 管理员且 password_hash 为 pwdlib 哈希")
async def test_migration_seed_admin_exists(database_url: str) -> None:
    """upgrade head 后存在 is_admin=true 的 seed 管理员且 password_hash 为 pwdlib 哈希。"""
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT email, is_admin, password_hash FROM users "
                "WHERE email = :email"
            ),
            {"email": _ADMIN_SEED_EMAIL},
        )
        user = row.mappings().first()
    await engine.dispose()

    assert user is not None
    assert bool(user["is_admin"]) is True
    assert user["password_hash"] != _ADMIN_SEED_PLAINTEXT_PASSWORD
    assert _hasher.verify(_ADMIN_SEED_PLAINTEXT_PASSWORD, user["password_hash"])
