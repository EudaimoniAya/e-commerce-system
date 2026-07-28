"""auth/user 域 HTTP helper。

§2（红阶段迁移中）：旧 ``register_user`` / ``register_authenticated`` 已移除；
新 helper ``send_sms_otp`` / ``register_user_via_otp`` / ``login_user_via_otp``
分别调用 ``/auth/sms/register`` 与 ``/auth/sms/login``。跨域测试迁移见 §6.2。
"""

from httpx import AsyncClient, Response

from app.user.schemas import TokenResponse
from tests.support.builders import (
    build_login_request,
    build_sms_login_request,
    build_sms_register_request,
    build_sms_send_request,
)
from tests.support.results import (
    LoginResult,
    SmsLoginResult,
    SmsRegisterResult,
    SmsSendResult,
)

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_PHONE = "13800000000"
_ADMIN_SEED_PASSWORD = "1919810810"


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


def _parse_token_body(response: Response) -> TokenResponse | None:
    """2xx 时解析 TokenResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return TokenResponse.model_validate(response.json())
    return None


async def send_sms_otp(
    client: AsyncClient,
    *,
    phone: str | None = None,
) -> SmsSendResult:
    """调用 POST /auth/sms/send，返回 SmsSendResult。"""
    request = build_sms_send_request(phone=phone)
    response: Response = await client.post(
        "/auth/sms/send",
        json=request.model_dump(mode="json"),
    )
    return SmsSendResult(
        status_code=response.status_code,
        phone=str(request.phone),
    )


async def register_user_via_otp(
    client: AsyncClient,
    *,
    phone: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
    code: str = "123456",
) -> SmsRegisterResult:
    """通过 POST /auth/sms/register 注册新用户，返回 SmsRegisterResult。

    需要先调用 ``send_sms_otp`` 写入 Redis OTP；默认使用固定 code "123456"
    （与 MockSmsProvider 一致）。
    """
    send_result = await send_sms_otp(client, phone=phone)
    request = build_sms_register_request(
        phone=send_result.phone,
        code=code,
        password=password,
        nickname=nickname,
    )
    response: Response = await client.post(
        "/auth/sms/register",
        json=request.model_dump(mode="json"),
    )
    return SmsRegisterResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        phone=send_result.phone,
        password=password,
    )


async def login_user(
    client: AsyncClient,
    *,
    identifier: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginResult:
    """调用 POST /auth/login（手机号 + 密码），返回 LoginResult。"""
    request = build_login_request(identifier=identifier, password=password)
    response: Response = await client.post(
        "/auth/login",
        json=request.model_dump(mode="json"),
    )
    return LoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        identifier=str(request.identifier),
        password=password,
    )


async def login_user_via_otp(
    client: AsyncClient,
    *,
    phone: str,
    code: str = "123456",
) -> SmsLoginResult:
    """通过 POST /auth/sms/login OTP 登录已有用户，返回 SmsLoginResult。

    需要先调用 ``send_sms_otp`` 写入 Redis OTP。
    """
    await send_sms_otp(client, phone=phone)
    request = build_sms_login_request(phone=phone, code=code)
    response: Response = await client.post(
        "/auth/sms/login",
        json=request.model_dump(mode="json"),
    )
    return SmsLoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        phone=phone,
    )


async def login_admin(client: AsyncClient) -> LoginResult:
    """使用 migration seed 管理员（手机号）登录，返回 LoginResult。"""
    return await login_user(
        client,
        identifier=_ADMIN_SEED_PHONE,
        password=_ADMIN_SEED_PASSWORD,
    )


# ── 兼容包装（过渡期，待 §6.2 全量迁移后移除） ─────────────────────────


async def register_user(
    client: AsyncClient,
    *,
    phone: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> SmsRegisterResult:
    """[Deprecated] 通过 OTP register 注册用户；新代码请改用 ``register_user_via_otp``。"""
    return await register_user_via_otp(
        client, phone=phone, password=password, nickname=nickname
    )


async def register_authenticated(client: AsyncClient) -> SmsRegisterResult:
    """[Deprecated] 注册用户；新代码请改用 ``register_user_via_otp``。"""
    return await register_user_via_otp(client)
