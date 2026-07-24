"""auth/user 域 HTTP helper。"""

from httpx import AsyncClient, Response

from app.user.schemas import TokenResponse
from tests.support.builders import build_login_request, build_register_request
from tests.support.results import LoginResult, RegisterResult

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"

# migration 003 seed 管理员凭据（见 alembic/versions/003_catalog_shop.py）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PASSWORD = "1919810810"


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


def _parse_token_body(response: Response) -> TokenResponse | None:
    """2xx 时解析 TokenResponse，否则返回 None。"""
    if 200 <= response.status_code < 300 and response.content:
        return TokenResponse.model_validate(response.json())
    return None


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> RegisterResult:
    """调用 POST /auth/register，返回 RegisterResult。"""
    request = build_register_request(
        email=email,
        password=password,
        nickname=nickname,
    )
    response: Response = await client.post(
        "/auth/register",
        json=request.model_dump(mode="json"),
    )
    return RegisterResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> LoginResult:
    """调用 POST /auth/login，返回 LoginResult。"""
    request = build_login_request(email=email, password=password)
    response: Response = await client.post(
        "/auth/login",
        json=request.model_dump(mode="json"),
    )
    return LoginResult(
        status_code=response.status_code,
        body=_parse_token_body(response),
        email=str(request.email),
        password=password,
    )


async def login_admin(client: AsyncClient) -> LoginResult:
    """使用 migration seed 管理员登录，返回 LoginResult。"""
    return await login_user(
        client,
        email=_ADMIN_SEED_EMAIL,
        password=_ADMIN_SEED_PASSWORD,
    )


async def register_authenticated(client: AsyncClient) -> RegisterResult:
    """注册用户，返回 RegisterResult。"""
    return await register_user(client)
