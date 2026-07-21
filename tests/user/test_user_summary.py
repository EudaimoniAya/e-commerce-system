"""user 域 UserService.get_user_summary service 层测试（TDD 红阶段）。

BDD 场景覆盖（对应 specs/ordering-seller-orders/spec.md Requirement 3）：
- 存在且 active 用户 → UserSummary（id + nickname）
- 不存在的 user_id → 404
- is_active=false 用户 → 422
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.models import User
from app.user.repository import UserRepository
from app.user.service import UserService
from tests.support.builders import unique_email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_active_user_returns_summary(
    db_session: AsyncSession,
) -> None:
    """存在且 active 的用户返回 UserSummary（含 id + nickname，不含 email）。"""
    repo = UserRepository(db_session)
    service = UserService(repo)
    email = unique_email("summary")
    user = await repo.create(
        user_id=uuid.uuid4(),
        email=email,
        password_hash="dummyhash",
        nickname="summary-test-user",
    )

    result = await service.get_user_summary(uuid.UUID(str(user.id)))

    assert result.id == str(user.id)
    assert result.nickname == "summary-test-user"
    # UserSummary 按设计不含 email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_not_found_returns_404(
    db_session: AsyncSession,
) -> None:
    """不存在的 user_id 返回 404。"""
    repo = UserRepository(db_session)
    service = UserService(repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_user_summary(uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_disabled_user_returns_422(
    db_session: AsyncSession,
) -> None:
    """is_active=false 的用户返回 422。"""
    disabled_user = User(
        id=uuid.uuid4(),
        email=unique_email("disabled-summary"),
        password_hash="dummyhash",
        nickname="disabled-summary",
        is_active=False,
    )
    db_session.add(disabled_user)
    await db_session.flush()

    repo = UserRepository(db_session)
    service = UserService(repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_user_summary(uuid.UUID(str(disabled_user.id)))
    assert exc_info.value.status_code == 422
