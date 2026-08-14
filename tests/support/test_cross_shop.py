"""support 域跨 shop 会话隔离 integration 测试（TDD 红阶段）。

覆盖：同一买家对不同 shop 拥有独立会话（(shop_id, buyer_user_id) 隔离）。
"""

import allure
import pytest
from httpx import AsyncClient

from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.support import (
    get_buyer_conversation,
    post_buyer_message,
)
from tests.testkit.utils import bearer_headers


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("support")
@allure.feature("cross_shop")
@allure.title("同一买家向两 shop 发消息后各自持有独立会话。")
async def test_cross_shop_buyer_has_independent_conversations(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    second_shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """同买家分别向 shop A 与 shop B 发首条消息 → 两条独立会话，shop_id 各异。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent_a = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="咨询A店",
    )
    assert sent_a.status_code == 201

    sent_b = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=second_shop_owner.shop_id,
        body="咨询B店",
    )
    assert sent_b.status_code == 201

    conv_a = await get_buyer_conversation(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert conv_a.status_code == 200
    assert conv_a.body is not None
    assert conv_a.body["shop_id"] == shop_owner.shop_id

    conv_b = await get_buyer_conversation(
        integration_client,
        headers=buyer_headers,
        shop_id=second_shop_owner.shop_id,
    )
    assert conv_b.status_code == 200
    assert conv_b.body is not None
    assert conv_b.body["shop_id"] == second_shop_owner.shop_id

    # 两条独立会话，id 不同
    assert conv_a.body["id"] != conv_b.body["id"]
    assert conv_a.body["buyer_user_id"] == conv_b.body["buyer_user_id"]
