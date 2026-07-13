"""JWT 签发/校验与 Bearer 鉴权依赖（不查库、不依赖业务域）。"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError

from app.infra.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    """签发 access token，返回 (token, expires_in 秒)。"""
    settings = get_settings()
    expire_minutes = settings.jwt_access_token_expire_minutes
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expire_minutes)
    expires_in = expire_minutes * 60
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "typ": "access",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def decode_access_token(token: str) -> uuid.UUID:
    """校验 access token 并返回用户 UUID；失败时抛出 HTTP 401。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except InvalidTokenError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    if payload.get("typ") != "access":
        raise _CREDENTIALS_EXCEPTION

    sub = payload.get("sub")
    if not sub:
        raise _CREDENTIALS_EXCEPTION

    try:
        return uuid.UUID(str(sub))
    except ValueError as exc:
        raise _CREDENTIALS_EXCEPTION from exc


async def get_current_user_id(
    token: str = Depends(oauth2_scheme),
) -> uuid.UUID:
    """从 Bearer token 解析当前用户 ID（不查库）。"""
    return decode_access_token(token)
