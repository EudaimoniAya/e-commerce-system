"""pytest 公共 fixture。"""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.main import app

# 本地 integration 测试默认连接 test 库（unix socket，与 .env.example 一致）
_DEFAULT_TEST_DATABASE_URL = (
    "mysql+asyncmy://root@localhost/ecommerce_test"
    "?charset=utf8mb4&unix_socket=/tmp/e-commerce-system-mysql.sock"
)

# integration 测试默认密码（符合 8–32 位规则）
_DEFAULT_TEST_PASSWORD = "password123"


@pytest.fixture(scope="session", autouse=True)
def _integration_test_database_url() -> None:
    """集成测试统一使用 ecommerce_test 库。"""
    url = os.environ.get("DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
    if "ecommerce_dev" in url:
        url = url.replace("ecommerce_dev", "ecommerce_test")
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("APP_ENV", "test")
    # JWT 配置为 Settings 必填项；集成测试使用固定测试密钥
    os.environ.setdefault(
        "JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes!!"
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    """当前测试会话使用的 MySQL 连接串（指向 ecommerce_test）。"""
    return os.environ["DATABASE_URL"]


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient，用于 HTTP 端点测试。"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def db_session(database_url: str) -> AsyncIterator[AsyncSession]:
    """每个测试在独立事务内执行，结束后 rollback 保证零副作用。"""
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


# --- auth integration 测试 helper ---


def unique_email(prefix: str = "user") -> str:
    """生成唯一测试邮箱，避免 integration 测试互相冲突。"""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


def register_user(
    client: TestClient,
    *,
    email: str | None = None,
    password: str = _DEFAULT_TEST_PASSWORD,
    nickname: str | None = None,
) -> dict[str, Any]:
    """调用 POST /auth/register，返回响应与请求上下文。"""
    payload: dict[str, str] = {
        "email": email or unique_email(),
        "password": password,
    }
    if nickname is not None:
        payload["nickname"] = nickname

    response = client.post("/auth/register", json=payload)
    body: Any | None
    if response.content:
        body = response.json()
    else:
        body = None

    return {
        "response": response,
        "status_code": response.status_code,
        "json": body,
        "email": payload["email"],
        "password": password,
    }


def login_user(
    client: TestClient,
    *,
    email: str,
    password: str = _DEFAULT_TEST_PASSWORD,
) -> dict[str, Any]:
    """调用 POST /auth/login，返回响应与请求上下文。"""
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    body: Any | None
    if response.content:
        body = response.json()
    else:
        body = None

    return {
        "response": response,
        "status_code": response.status_code,
        "json": body,
        "email": email,
        "password": password,
    }


@pytest.fixture
def authenticated_user(client: TestClient) -> dict[str, Any]:
    """注册成功并返回 access_token 与 Bearer 请求头（供 /users/me 等已认证端点）。"""
    registered = register_user(client)
    if registered["status_code"] != 201 or not registered["json"]:
        return {
            **registered,
            "access_token": None,
            "headers": {},
        }

    access_token = registered["json"]["access_token"]
    return {
        **registered,
        "access_token": access_token,
        "headers": auth_headers(access_token),
        "user": registered["json"].get("user"),
    }
