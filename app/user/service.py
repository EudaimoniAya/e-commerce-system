"""user 域业务逻辑（注册、登录、密码哈希）。"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.infra.auth import create_access_token
from app.media.service import MediaService
from app.user.phone import normalize_phone
from app.user.repository import UserRepository
from app.user.schemas import (
    LoginRequest,
    SmsLoginRequest,
    SmsRegisterRequest,
    SmsSendRequest,
    TokenResponse,
    UserProfileUpdateRequest,
    UserResponse,
    UserSummary,
)
from app.user.sms_service import SmsOtpService

_hasher = PasswordHash.recommended()

_INVALID_CREDENTIALS_MSG = "Invalid phone or password"
_INVALID_OTP_MSG = "Invalid or expired verification code"


def _default_nickname() -> str:
    """未提供昵称时生成默认昵称（用户_ + 毫秒级时间戳）。"""
    now = datetime.now()
    return f"用户_{now.strftime('%Y%m%d%H%M%S')}{now.microsecond // 1000:03d}"


def _to_user_response(user, avatar_url: str | None = None) -> UserResponse:
    """ORM 用户转对外 DTO。"""
    return UserResponse(
        id=str(user.id),
        phone=user.phone or "",
        email=user.email,
        nickname=user.nickname,
        avatar_url=avatar_url,
        created_at=user.created_at,
    )


async def _resolve_avatar_url(
    media_service: MediaService,
    user,
) -> str | None:
    """解析 user.avatar_media_id → avatar_url（缺失 media 行 → None）。"""
    media_id = getattr(user, "avatar_media_id", None)
    if media_id is None:
        return None
    media_id_str = str(media_id)
    urls = await media_service.resolve_urls([media_id_str])
    return urls.get(media_id_str)


async def _build_token_response(
    user,
    media_service: MediaService,
) -> TokenResponse:
    """签发 token 并组装响应（avatar_url 经 media 域 resolve）。"""
    user_uuid = uuid.UUID(str(user.id))
    access_token, expires_in = create_access_token(user_uuid)
    avatar_url = await _resolve_avatar_url(media_service, user)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_to_user_response(user, avatar_url=avatar_url),
    )


def _normalize_or_422(raw: str) -> str:
    """规范化手机号，非法时 422。"""
    phone = normalize_phone(raw)
    if phone is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid phone number",
        )
    return phone


class UserService:
    """用户注册与登录服务。"""

    def __init__(
        self,
        repository: UserRepository,
        sms: SmsOtpService,
        media_service: MediaService,
    ) -> None:
        self._repository = repository
        self._sms = sms
        self._media_service = media_service

    async def send_sms(self, data: SmsSendRequest) -> None:
        """发送 SMS OTP（不区分用户是否存在）。"""
        phone = _normalize_or_422(data.phone)
        await self._sms.send_otp(phone)

    async def _verify_otp_or_raise(self, phone: str, code: str) -> None:
        """校验 OTP；失败时累计 verify_fail 并 422。"""
        await self._sms.ensure_verify_allowed(phone)
        if not await self._sms.consume_otp(phone, code):
            await self._sms.record_verify_failure(phone)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_INVALID_OTP_MSG,
            )

    async def register_via_sms(self, data: SmsRegisterRequest) -> TokenResponse:
        """SMS OTP 注册新用户。"""
        phone = _normalize_or_422(data.phone)
        await self._verify_otp_or_raise(phone, data.code)

        existing = await self._repository.get_by_phone(phone)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Phone already registered",
            )

        nickname = data.nickname.strip() if data.nickname else ""
        if not nickname:
            nickname = _default_nickname()

        password_hash = _hasher.hash(data.password)
        user = await self._repository.create(
            user_id=uuid.uuid4(),
            phone=phone,
            password_hash=password_hash,
            nickname=nickname,
        )
        await self._sms.clear_verify_fail(phone)
        return await _build_token_response(user, self._media_service)

    async def login_via_sms(self, data: SmsLoginRequest) -> TokenResponse:
        """SMS OTP 登录已有用户。"""
        phone = _normalize_or_422(data.phone)
        await self._verify_otp_or_raise(phone, data.code)

        user = await self._repository.get_by_phone(phone)
        if user is None:
            await self._sms.record_verify_failure(phone)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_INVALID_OTP_MSG,
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        await self._sms.clear_verify_fail(phone)
        return await _build_token_response(user, self._media_service)

    async def get_user_summary(self, user_id: uuid.UUID | str) -> UserSummary:
        """查询用户摘要（跨域只读）。"""
        user = await self._repository.get_by_id(uuid.UUID(str(user_id)))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="User account is disabled",
            )
        return UserSummary(id=str(user.id), nickname=user.nickname)

    async def login(self, data: LoginRequest) -> TokenResponse:
        """通过手机号 + 密码校验凭据并返回 access token。"""
        phone = _normalize_or_422(data.identifier)
        user = await self._repository.get_by_phone(phone)
        if (
            user is None
            or user.password_hash is None
            or not _hasher.verify(data.password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "INVALID_CREDENTIALS",
                    "message": _INVALID_CREDENTIALS_MSG,
                },
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return await _build_token_response(user, self._media_service)

    async def update_profile(
        self,
        user_id: uuid.UUID,
        data: UserProfileUpdateRequest,
    ) -> UserResponse:
        """更新当前用户资料（email / nickname / avatar_media_id），校验 email 唯一性。

        avatar attach：设置 ``avatar_media_id`` 时校验 owner（403）+ ``image/*``（422），
        成功后同事务 ``mark_public``；显式 null 表示清空头像引用。
        """
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if data.email is not None:
            existing = await self._repository.get_by_email(data.email)
            if existing is not None and str(existing.id) != str(user.id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Email already used",
                )

        # 仅更新客户端显式传入的字段（None = 清空）
        update_kwargs = data.model_dump(exclude_unset=True)
        avatar_media_id = update_kwargs.get("avatar_media_id")

        # attach 校验 + mark_public 须在 commit 前（与 FK 写同事务）
        if avatar_media_id is not None:
            await self._media_service.assert_owned_by(avatar_media_id, str(user_id))
            await self._media_service.assert_image_content_type(avatar_media_id)
            await self._media_service.mark_public(avatar_media_id)

        updated = await self._repository.update_profile(user, **update_kwargs)
        avatar_url = await _resolve_avatar_url(self._media_service, updated)
        return _to_user_response(updated, avatar_url=avatar_url)
