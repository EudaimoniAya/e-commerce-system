"""infra/auth JWT 编解码单元测试。"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from app.infra.auth import create_access_token, decode_access_token
from app.infra.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """每个测试前清 Settings 缓存，避免环境变量污染。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_and_decode_access_token_roundtrip() -> None:
    """有效 token 编解码应返回相同用户 UUID。"""
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id)

    assert isinstance(token, str)
    assert expires_in == get_settings().jwt_access_token_expire_minutes * 60
    assert decode_access_token(token) == user_id


def test_decode_rejects_expired_token() -> None:
    """过期 token 应被拒绝。"""
    settings = get_settings()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "iat": int((now - timedelta(hours=1)).timestamp()),
        "exp": int((now - timedelta(minutes=1)).timestamp()),
        "typ": "access",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)

    assert exc_info.value.status_code == 401


def test_decode_rejects_wrong_typ() -> None:
    """typ 非 access 的 token 应被拒绝。"""
    settings = get_settings()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "typ": "refresh",
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)

    assert exc_info.value.status_code == 401
