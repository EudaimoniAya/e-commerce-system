"""SMS OTP 服务层：OTP 生成/消费、日发送限流、验证失败计数与 Mock SMS Provider。

设计要点
========
- Redis key 均使用规范化 11 位手机号
- OTP 消费使用 GETDEL（Redis 8），原子防止重复消费
- 日发送上限 ``sms:daily:{phone}:{date}``（TTL 86400s）
- 验证失败计数 ``sms:verify_fail:{phone}``（TTL 900s，默认 5 次后 429）
"""

import logging
import random
from datetime import UTC

import redis.asyncio as aioredis
from fastapi import HTTPException, status

from app.infra.config import Settings

logger = logging.getLogger(__name__)

_VERIFY_FAIL_WINDOW_SECONDS = 900


def _otp_key(phone: str) -> str:
    return f"sms:otp:{phone}"


def _daily_key(phone: str) -> str:
    """日发送计数 key（按 UTC 日期轮转）。"""
    from datetime import datetime

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    return f"sms:daily:{phone}:{date_str}"


def _verify_fail_key(phone: str) -> str:
    return f"sms:verify_fail:{phone}"


def _generate_otp(fixed_code: str | None) -> str:
    """生成 6 位数字 OTP；存在固定 code 时返回该 code。"""
    if fixed_code is not None:
        return fixed_code
    return f"{random.randint(0, 999999):06d}"


class MockSmsProvider:
    """Mock SMS 提供商（dev/test/CI：仅日志，不真实发送）。"""

    @staticmethod
    def send(phone: str, code: str) -> None:
        """模拟发送验证码到指定手机号。"""
        logger.info("Mock SMS send to %s: code=%s", phone, code)


class SmsOtpService:
    """SMS OTP 服务：发送验证码、原子消费、日发送限流与验证失败计数。"""

    def __init__(self, redis: aioredis.Redis, settings: Settings | None = None) -> None:
        self._redis = redis
        self._settings = settings

    @property
    def _ttl(self) -> int:
        return self._settings.sms_otp_ttl_seconds if self._settings else 300

    @property
    def _daily_limit(self) -> int:
        return self._settings.sms_daily_send_limit if self._settings else 10

    @property
    def _verify_fail_limit(self) -> int:
        return self._settings.sms_verify_fail_limit if self._settings else 5

    @property
    def _verify_fail_window(self) -> int:
        if self._settings is not None:
            return self._settings.sms_verify_fail_window_seconds
        return _VERIFY_FAIL_WINDOW_SECONDS

    @property
    def _fixed_code(self) -> str | None:
        return self._settings.sms_otp_fixed_code if self._settings else None

    async def send_otp(self, phone: str) -> None:
        """生成 OTP、写入 Redis、Mock 发送。

        Raises:
            HTTPException(429) — 日发送次数超限
        """
        daily_key = _daily_key(phone)
        daily_raw = await self._redis.get(daily_key)
        if daily_raw is not None and int(daily_raw) >= self._daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily SMS send limit exceeded",
            )

        code = _generate_otp(self._fixed_code)
        await self._redis.setex(_otp_key(phone), self._ttl, code)

        await self._redis.incr(daily_key)
        await self._redis.expire(daily_key, 86400)

        MockSmsProvider.send(phone, code)

    async def ensure_verify_allowed(self, phone: str) -> None:
        """验证失败未超限时通过；已达上限则 429。"""
        fail_key = _verify_fail_key(phone)
        raw = await self._redis.get(fail_key)
        if raw is not None and int(raw) >= self._verify_fail_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification attempts",
            )

    async def record_verify_failure(self, phone: str) -> None:
        """记录一次 OTP 验证失败（含错误码、过期、login 用户不存在等）。"""
        fail_key = _verify_fail_key(phone)
        count = await self._redis.incr(fail_key)
        if count == 1:
            await self._redis.expire(fail_key, self._verify_fail_window)

    async def clear_verify_fail(self, phone: str) -> None:
        """register/login 成功后复位验证失败计数。"""
        await self._redis.delete(_verify_fail_key(phone))

    async def consume_otp(self, phone: str, code: str) -> bool:
        """原子消费 OTP（GETDEL），返回 True 表示匹配。"""
        stored = await self._redis.getdel(_otp_key(phone))
        if stored is None:
            return False
        stored_str = stored.decode() if isinstance(stored, bytes) else str(stored)
        return stored_str == code
