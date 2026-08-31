"""ai 域 AI 回复端点 ``POST /ai/shops/{shop_id}/replies`` integration 测试（TDD 红阶段）。

覆盖 spec ai-http-replies 全部场景：
- 守卫：未认证 401；认证买家无会话 404 且 SHALL NOT 建会话/消息
- 有问句 200：响应含 ``text`` / ``conversation_id`` / ``assistant_message_id``，
  messages 落 ``author_role=ai`` / ``sender_role=shop`` 助手行
- 回看：先卡片后问句 → 知识路径 ``product_id`` 为卡片 id；助手行切断回看（不粘墙外旧 ref）
- 纯卡片问候：``text`` 为 ``ask_about_product`` 模板（非 ``suggest_human``）
- 生成抛错仍 200：正文为 ``suggest_human``

注入：``build_intent_controller`` dependency override（ADR-013 决策 1，router 以
``Depends`` 消费）。**不编写** router / 落库接线 / 回看 / 失败兜底 / ``ask_about_product.yaml``
（红阶段，路由缺失 → 404 即红；符号类断言另见 ``tests/unit/ai/test_domain_composition.py``）。
"""

import allure
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import FakeLLMClient
from tests.ai.testkit.pipeline import (
    NLU_KNOWLEDGE_JSON,
    build_controller,
    override_intent_controller,
)
from tests.testkit.contexts import AuthContext, ShopOwnerContext
from tests.testkit.helper.ai import post_ai_reply
from tests.testkit.helper.ordering import arrange_purchasable_product
from tests.testkit.helper.support import (
    get_buyer_conversation,
    list_buyer_messages,
    post_buyer_message,
)
from tests.testkit.utils import bearer_headers

_UNKNOWN_SHOP_ID = "00000000-0000-0000-0000-000000000000"
_ANSWER = "这件商品支持七天无理由退换。"


def _product_ref(product_id: str) -> dict[str, str]:
    return {"ref_type": "product", "ref_id": product_id}


def _registered_prompt_text(prompt_id: str) -> str:
    """读取已登记提示词正文（经 ``app.ai.deps.build_prompt_loader``）。"""
    from app.ai.deps import build_prompt_loader

    return build_prompt_loader().load(prompt_id).text


class _RaisingGenerationLLM:
    """生成阶段抛错的 LLM：``generate`` 一律抛错（模拟 LLM/编排失败）。"""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        raise RuntimeError("LLM 服务不可用")


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("未认证 POST replies 返回 401。")
async def test_replies_unauthenticated_returns_401(client: AsyncClient) -> None:
    """未认证客户端 POST replies：401（鉴权先于业务校验）。"""
    result = await post_ai_reply(client, headers={}, shop_id=_UNKNOWN_SHOP_ID)

    assert result.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("认证买家无会话 POST replies 返回 404 且不建会话。")
async def test_replies_no_conversation_returns_404_without_side_effect(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """认证买家对该 shop 尚无会话：404，且 SHALL NOT 创建会话或消息。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)

    result = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert result.status_code == 404

    conversation = await get_buyer_conversation(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert conversation.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("买家先发问再 POST replies：200 且响应含助手正文与会话/消息 id。")
async def test_replies_after_question_returns_200_with_assistant_row(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """买家 POST 非空 body 后 POST replies → 200，响应三字段齐备，messages 落 ai 行。"""
    override_intent_controller(
        build_controller(
            nlu_output=NLU_KNOWLEDGE_JSON,
            generation_llm=FakeLLMClient(output=_ANSWER),
        )
    )
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="这款包是什么材质？",
    )
    assert sent.status_code == 201
    assert sent.body is not None

    replied = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert replied.status_code == 200
    assert replied.body is not None
    assert replied.body["text"] == _ANSWER
    assert replied.body["conversation_id"] == sent.body["conversation_id"]
    assert replied.body["assistant_message_id"]

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
    assert items[1]["body"] == _ANSWER
    assert items[1]["id"] == replied.body["assistant_message_id"]


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("先卡片后问句：回看按卡片 ref 过滤 product_id。")
async def test_replies_lookback_uses_card_product_ref(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """卡片（ref A）→ 无 refs 问句 → replies：retrieve 的 product_id 为 A，query 为问句。"""
    records: list[dict] = []
    override_intent_controller(
        build_controller(
            nlu_output=NLU_KNOWLEDGE_JSON,
            generation_llm=FakeLLMClient(output="已回答"),
            records=records,
        )
    )
    buyer_headers = bearer_headers(authenticated_user.access_token)
    _, product_id = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id
    )

    card = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )
    assert card.status_code == 201

    question = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="这款包能放多久？",
    )
    assert question.status_code == 201

    replied = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert replied.status_code == 200
    assert len(records) == 1
    assert records[0]["query"] == "这款包能放多久？"
    assert records[0]["product_id"] == product_id


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("助手行切断回看：墙外旧 ref 不得粘到新问句。")
async def test_replies_lookback_stops_at_assistant_wall(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """卡片（ref A）→ 问句 1 → replies（落助手墙）→ 问句 2 → replies：本轮不粘 A。"""
    records: list[dict] = []
    override_intent_controller(
        build_controller(
            nlu_output=NLU_KNOWLEDGE_JSON,
            generation_llm=FakeLLMClient(output="已回答"),
            records=records,
        )
    )
    buyer_headers = bearer_headers(authenticated_user.access_token)
    _, product_id = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id
    )

    card = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )
    assert card.status_code == 201
    first = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="第一问",
    )
    assert first.status_code == 201

    first_reply = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert first_reply.status_code == 200
    assert len(records) == 1
    assert records[0]["product_id"] == product_id

    second = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="第二问",
    )
    assert second.status_code == 201

    second_reply = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert second_reply.status_code == 200
    assert len(records) == 2
    assert records[1]["query"] == "第二问"
    assert records[1]["product_id"] is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("纯卡片 POST replies：200 且 text 为问候模板（非转人工）。")
async def test_replies_card_only_returns_greeting(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """仅含 product ref 无 body 后 POST replies：问候文案 + ai 行，不用 suggest_human。"""
    buyer_headers = bearer_headers(authenticated_user.access_token)
    _, product_id = await arrange_purchasable_product(
        db_session, shop_id=shop_owner.shop_id
    )
    card = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        message_refs=[_product_ref(product_id)],
    )
    assert card.status_code == 201

    replied = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert replied.status_code == 200
    assert replied.body is not None
    greeting = _registered_prompt_text("ask_about_product")
    human_fallback = _registered_prompt_text("suggest_human")
    assert replied.body["text"] == greeting
    assert replied.body["text"] != human_fallback

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
    assert items[1]["body"] == greeting


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("replies")
@allure.title("生成抛错时 POST replies 仍 200 且落 suggest_human 助手行。")
async def test_replies_generation_failure_still_200_with_fallback(
    integration_client: AsyncClient,
    shop_owner: ShopOwnerContext,
    authenticated_user: AuthContext,
) -> None:
    """生成 LLM 抛错 → 200，正文为 suggest_human，落 author_role=ai 行。"""
    override_intent_controller(
        build_controller(
            nlu_output=NLU_KNOWLEDGE_JSON,
            generation_llm=_RaisingGenerationLLM(),  # type: ignore[arg-type]
        )
    )
    buyer_headers = bearer_headers(authenticated_user.access_token)

    sent = await post_buyer_message(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
        body="请问这个多少钱？",
    )
    assert sent.status_code == 201

    replied = await post_ai_reply(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )

    assert replied.status_code == 200
    assert replied.body is not None
    fallback = _registered_prompt_text("suggest_human")
    assert replied.body["text"] == fallback

    messages = await list_buyer_messages(
        integration_client,
        headers=buyer_headers,
        shop_id=shop_owner.shop_id,
    )
    assert messages.status_code == 200
    assert messages.body is not None
    items = messages.body["items"]
    assert items[-1]["author_role"] == "ai"
    assert items[-1]["sender_role"] == "shop"
    assert items[-1]["body"] == fallback
