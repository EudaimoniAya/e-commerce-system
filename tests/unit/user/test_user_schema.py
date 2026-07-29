"""user 域 request schema 格式边界单元测试。

RegisterRequest 已随 email 注册路径移除；LoginRequest 改为 identifier + password。
SMS 注册/登录拆分为 SmsRegisterRequest 与 SmsLoginRequest。
"""

import allure
import pytest
from pydantic import ValidationError

from app.user.schemas import (
    LoginRequest,
    SmsLoginRequest,
    SmsRegisterRequest,
    SmsSendRequest,
)

# 非法 password 用例（LoginRequest / SmsRegisterRequest 共用 Field 约束）
_INVALID_PASSWORDS = [
    pytest.param("short", id="too_short_7"),
    pytest.param("a" * 33, id="too_long_33"),
]

_TEST_IDENTIFIER = "13800138000"


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("LoginRequest 对非法 password 抛出 ValidationError。")
@pytest.mark.parametrize("password", _INVALID_PASSWORDS)
def test_login_request_rejects_invalid_password(password: str) -> None:
    """LoginRequest 对非法 password 抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        LoginRequest(identifier=_TEST_IDENTIFIER, password=password)


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsRegisterRequest 对非法 password 抛出 ValidationError。")
@pytest.mark.parametrize("password", _INVALID_PASSWORDS)
def test_sms_register_request_rejects_invalid_password(password: str) -> None:
    """SmsRegisterRequest 对非法 password 抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        SmsRegisterRequest(phone="13800138000", code="123456", password=password)


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsSendRequest 接受任意字符串 phone（校验在 service 层）。")
def test_sms_send_request_accepts_valid_phone() -> None:
    """SmsSendRequest 接受任意字符串 phone（校验在 service 层）。"""
    request = SmsSendRequest(phone="13800138000")
    assert request.phone == "13800138000"


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsRegisterRequest 接受合法字段。")
def test_sms_register_request_accepts_valid_data() -> None:
    """SmsRegisterRequest 接受合法字段。"""
    request = SmsRegisterRequest(
        phone="13800138000",
        code="123456",
        password="password123",
        nickname="test",
    )
    assert request.phone == "13800138000"
    assert request.code == "123456"
    assert request.password == "password123"
    assert request.nickname == "test"


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsLoginRequest 接受 phone + code，不含 password。")
def test_sms_login_request_accepts_valid_data() -> None:
    """SmsLoginRequest 接受 phone + code，不含 password。"""
    request = SmsLoginRequest(phone="13800138000", code="123456")
    assert request.phone == "13800138000"
    assert request.code == "123456"


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsRegisterRequest code 少于 6 位抛出 ValidationError。")
def test_sms_register_request_code_too_short_rejected() -> None:
    """SmsRegisterRequest code 少于 6 位抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        SmsRegisterRequest(
            phone="13800138000", code="12345", password="password123"
        )


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsLoginRequest code 多于 6 位抛出 ValidationError。")
def test_sms_login_request_code_too_long_rejected() -> None:
    """SmsLoginRequest code 多于 6 位抛出 ValidationError。"""
    with pytest.raises(ValidationError):
        SmsLoginRequest(phone="13800138000", code="1234567")


@allure.epic("user")
@allure.feature("user_schema")
@allure.title("SmsRegisterRequest password 为必填（schema 层）。")
def test_sms_register_request_password_required() -> None:
    """SmsRegisterRequest password 为必填（schema 层）。"""
    request = SmsRegisterRequest(phone="13800138000", code="123456", password="password123")
    assert request.password == "password123"
