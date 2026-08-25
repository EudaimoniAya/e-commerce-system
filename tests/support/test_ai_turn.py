"""support 域 AI 回合 integration 测试（TDD 红阶段）。

覆盖 spec support-conversations「AI port on buyer POST when mode is ai」：
- 注入 Mock Port 返回固定文案：买家 POST 201 仍为买家行，GET messages 含随后
  ``author_role=ai`` / ``sender_role=shop`` 的助手行
- Port 抛错：买家仍 201，且落兜底助手行（``author_role=ai`` / ``sender_role=shop``，正文非空）
- 未注入工厂且模式为 ai：买家 201 不 500，且落同一兜底助手行

注入点：``app.support.deps.register_buyer_turn_handler_factory``（不 import ``app.ai``）。
**不编写** service 接线（红阶段，注入 API 缺失 → 导入失败即红）。
"""

from collections.abc import AsyncIterator

import allure
import pytest
from httpx import AsyncClient

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.support import list_buyer_messages, post_buyer_message
from tests.testkit.utils import bearer_headers


class MockBuyerTurnAiHandler:
    """可编程 Mock Port：返回固定正文或抛错（红阶段不 import ``app.ai``）。"""

    def __init__(self, *, reply: str | None = None, raise_error: bool = False) -> None:
        self._reply = reply
        self._raise_error = raise_error

    async def handle_buyer_turn(
        self,
        *,
        shop_id: str,
        body: str | None,
        product_ref_ids: list[str],
    ) -> str:
        if self._raise_error:
            raise RuntimeError("LLM 服务不可用")
        assert self._reply is not None
        return self._reply


@pytest.fixture(autouse=True)
async def _reset_buyer_turn_factory() -> AsyncIterator[None]:
    """每个用例前后把 Port 工厂重置为「未注入」（工厂返回 None → 兜底分支）。"""
    from app.support.deps import register_buyer_turn_handler_factory

    register_buyer_turn_handler_factory(lambda: None)
    yield
    register_buyer_turn_handler_factory(lambda: None)


def _inject_port(reply: str | None = None, *, raise_error: bool = False) -> None:
    """将可编程 Mock Port 工厂注入 support deps（红阶段 API 未实现 → 导入失败即红）。"""
    from app.support.deps import register_buyer_turn_handler_factory

    register_buyer_turn_handler_factory(
        lambda: MockBuyerTurnAiHandler(reply=reply, raise_error=raise_error)
    )


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("ai_turn")
@allure.title("注入 Mock Port 时买家 POST 201 仍为买家行，GET messages 含 AI 助手行。")
async def test_buyer_post_with_mock_port_writes_ai_followup(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """Port 返回固定文案：POST 响应仍是买家行；messages 随后含 author_role=ai / sender_role=shop。"""
    _inject_port(reply="这是 AI 回复")
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201
    assert sent.body is not None
    assert sent.body["author_role"] == "human"
    assert sent.body["sender_role"] == "buyer"

    messages = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert messages.status_code == 200
    assert messages.body is not None
    items = messages.body["items"]
    assert len(items) == 2
    assert items[0]["author_role"] == "human"
    assert items[0]["sender_role"] == "buyer"
    assert items[1]["author_role"] == "ai"
    assert items[1]["sender_role"] == "shop"
    assert items[1]["body"] == "这是 AI 回复"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("ai_turn")
@allure.title("Port 抛错时买家 POST 仍 201 且落兜底助手行。")
async def test_buyer_post_when_port_raises_returns_201_with_fallback(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """Port 抛错不 5xx：买家消息仍在，且落一条正文非空的兜底助手行。"""
    _inject_port(raise_error=True)
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201
    assert sent.body is not None
    assert sent.body["author_role"] == "human"

    messages = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert messages.status_code == 200
    assert messages.body is not None
    items = messages.body["items"]
    assert len(items) == 2
    assert items[1]["author_role"] == "ai"
    assert items[1]["sender_role"] == "shop"
    assert items[1]["body"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("ai_turn")
@allure.title("未注入工厂且模式为 ai 时买家 POST 仍 201 且落兜底助手行。")
async def test_buyer_post_uninjected_factory_returns_201_with_fallback(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """不注入 Port：默认 handler_mode=ai → 落兜底助手行，SHALL NOT 500。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="你好",
    )
    assert sent.status_code == 201
    assert sent.body is not None
    assert sent.body["author_role"] == "human"

    messages = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert messages.status_code == 200
    assert messages.body is not None
    items = messages.body["items"]
    assert len(items) == 2
    assert items[1]["author_role"] == "ai"
    assert items[1]["sender_role"] == "shop"
    assert items[1]["body"]
