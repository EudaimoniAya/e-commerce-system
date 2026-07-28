"""SmsOtpService 验证失败计数单元测试。"""

from unittest.mock import AsyncMock

import allure
import pytest
from fastapi import HTTPException

from app.infra.config import Settings
from app.user.sms_service import SmsOtpService


@pytest.fixture
def mock_redis() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sms_service(mock_redis: AsyncMock) -> SmsOtpService:
    settings = Settings(
        database_url="mysql+asyncmy://u:p@localhost/db",
        redis_url="redis://127.0.0.1:6379/1",
        jwt_secret_key="x" * 32,
        sms_verify_fail_limit=3,
        sms_verify_fail_window_seconds=900,
    )
    return SmsOtpService(mock_redis, settings)


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("无失败记录时不抛异常。")
@pytest.mark.asyncio
async def test_ensure_verify_allowed_passes_when_no_failures(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """无失败记录时不抛异常。"""
    mock_redis.get.return_value = None
    await sms_service.ensure_verify_allowed("13800138000")
    mock_redis.get.assert_awaited_once()


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("失败次数达到上限时 429。")
@pytest.mark.asyncio
async def test_ensure_verify_allowed_raises_429_at_limit(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """失败次数达到上限时 429。"""
    mock_redis.get.return_value = b"3"
    with pytest.raises(HTTPException) as exc_info:
        await sms_service.ensure_verify_allowed("13800138000")
    assert exc_info.value.status_code == 429


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("首次失败写入计数并设置 TTL。")
@pytest.mark.asyncio
async def test_record_verify_failure_sets_ttl_on_first(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """首次失败写入计数并设置 TTL。"""
    mock_redis.incr.return_value = 1
    await sms_service.record_verify_failure("13800138000")
    mock_redis.incr.assert_awaited_once()
    mock_redis.expire.assert_awaited_once_with("sms:verify_fail:13800138000", 900)


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("成功后删除 verify_fail key。")
@pytest.mark.asyncio
async def test_clear_verify_fail_deletes_key(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """成功后删除 verify_fail key。"""
    await sms_service.clear_verify_fail("13800138000")
    mock_redis.delete.assert_awaited_once_with("sms:verify_fail:13800138000")


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("GETDEL 匹配时返回 True。")
@pytest.mark.asyncio
async def test_consume_otp_returns_true_on_match(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """GETDEL 匹配时返回 True。"""
    mock_redis.getdel.return_value = b"123456"
    assert await sms_service.consume_otp("13800138000", "123456") is True


@allure.epic("user")
@allure.feature("sms_service")
@allure.title("OTP 不存在时返回 False。")
@pytest.mark.asyncio
async def test_consume_otp_returns_false_when_missing(
    sms_service: SmsOtpService, mock_redis: AsyncMock
) -> None:
    """OTP 不存在时返回 False。"""
    mock_redis.getdel.return_value = None
    assert await sms_service.consume_otp("13800138000", "123456") is False
