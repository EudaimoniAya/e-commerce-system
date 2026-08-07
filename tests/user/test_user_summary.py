"""user 域 UserService.get_user_summary service 层测试（TDD 红阶段）。

探针例外（design D10）：纯 service + rollback ``db_session``，无 HTTP。
BDD 场景覆盖（对应 specs/ordering-seller-orders/spec.md Requirement 3）：
- 存在且 active 用户 → UserSummary（id + nickname）
- 不存在的 user_id → 404
- is_active=false 用户 → 422
"""

import uuid
from unittest.mock import AsyncMock

import allure
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.repository import UserRepository
from app.user.service import UserService
from app.user.sms_service import SmsOtpService
from tests.support.builders import unique_phone
from tests.support.db.user import seed_active_user, seed_inactive_user


def _user_service(repo: UserRepository) -> UserService:
    """纯 DB 测试用 UserService（SMS / media 依赖占位）。"""
    return UserService(
        repo,
        SmsOtpService(AsyncMock()),
        media_service=AsyncMock(),
    )


@allure.epic("user")
@allure.feature("user_summary")
@allure.title("存在且 active 的用户返回 UserSummary（含 id + nickname，不含 email）。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_active_user_returns_summary(
    db_session: AsyncSession,
) -> None:
    """存在且 active 的用户返回 UserSummary（含 id + nickname，不含 email）。"""
    user_id = await seed_active_user(
        db_session,
        phone=unique_phone(),
        nickname="summary-test-user",
    )

    repo = UserRepository(db_session)
    service = _user_service(repo)
    result = await service.get_user_summary(uuid.UUID(user_id))

    assert result.id == user_id
    assert result.nickname == "summary-test-user"
    # UserSummary 按设计不含 email


@allure.epic("user")
@allure.feature("user_summary")
@allure.title("不存在的 user_id 返回 404。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_not_found_returns_404(
    db_session: AsyncSession,
) -> None:
    """不存在的 user_id 返回 404。"""
    repo = UserRepository(db_session)
    service = _user_service(repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_user_summary(uuid.uuid4())
    assert exc_info.value.status_code == 404


@allure.epic("user")
@allure.feature("user_summary")
@allure.title("is_active=false 的用户返回 422。")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_user_summary_disabled_user_returns_422(
    db_session: AsyncSession,
) -> None:
    """is_active=false 的用户返回 422。"""
    user_id = await seed_inactive_user(
        db_session,
        phone=unique_phone(),
        password="dummy-password",
    )

    repo = UserRepository(db_session)
    service = _user_service(repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_user_summary(uuid.UUID(user_id))
    assert exc_info.value.status_code == 422
