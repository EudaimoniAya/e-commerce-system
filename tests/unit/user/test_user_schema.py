"""user 域 request schema 格式边界单元测试。"""

import pytest
from pydantic import ValidationError

from app.user.schemas import LoginRequest, RegisterRequest

# 非法 password 用例（RegisterRequest / LoginRequest 共用 Field 约束）
_INVALID_PASSWORDS = [
    pytest.param("short", id="too_short_7"),
    pytest.param("a" * 33, id="too_long_33"),
]

_TEST_EMAIL = "user@example.com"


@pytest.mark.parametrize("password", _INVALID_PASSWORDS)
def test_register_request_rejects_invalid_password(password: str) -> None:
    """RegisterRequest 对非法 password 抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        RegisterRequest(email=_TEST_EMAIL, password=password)


@pytest.mark.parametrize("password", _INVALID_PASSWORDS)
def test_login_request_rejects_invalid_password(password: str) -> None:
    """LoginRequest 对非法 password 抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        LoginRequest(email=_TEST_EMAIL, password=password)
