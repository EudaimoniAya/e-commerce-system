"""LLM 客户端单测（TDD 绿阶段）。

覆盖 spec ai-support-agent「LLM client protocol with mock and DeepSeek」：
- FakeLLMClient 返回编程输出（str / JSON dict），不访问网络
- DeepSeekClient 经 httpx mock 返回 ``choices[0].message.content``，请求发往
  ``{base_url}/chat/completions`` 且带 Authorization（不打真网）
"""

import json

import allure
import httpx
import pytest

from app.ai.llm import client as llm_client
from app.ai.llm.client import DeepSeekClient, FakeLLMClient


@allure.epic("ai")
@allure.feature("llm_client")
@allure.title("FakeLLMClient 返回编程 JSON 输出。")
@pytest.mark.asyncio
async def test_fake_llm_returns_programmed_json() -> None:
    """dict 输出序列化为 JSON 字符串（供 NL 网关解析）。"""
    client = FakeLLMClient(output={"intent": "knowledge", "confidence": 0.9})

    text = await client.generate([{"role": "user", "content": "这款包怎么样"}])

    assert json.loads(text) == {"intent": "knowledge", "confidence": 0.9}
    assert len(client.calls) == 1


@allure.epic("ai")
@allure.feature("llm_client")
@allure.title("FakeLLMClient 原样返回 str 输出。")
@pytest.mark.asyncio
async def test_fake_llm_returns_plain_string() -> None:
    """str 输出原样返回（生成答案场景）。"""
    client = FakeLLMClient(output="你好，这是答案")

    text = await client.generate([{"role": "user", "content": "你好"}])

    assert text == "你好，这是答案"


@allure.epic("ai")
@allure.feature("llm_client")
@allure.title("MockLLMClient 产品类已移除。")
def test_no_mock_llm_client_class_remains() -> None:
    """app.ai.llm.client 不得再保留 MockLLMClient。"""
    assert not hasattr(llm_client, "MockLLMClient")


@allure.epic("ai")
@allure.feature("llm_client")
@allure.title("DeepSeekClient httpx mock 下返回 content。")
@pytest.mark.asyncio
async def test_deepseek_client_mock_http_returns_content() -> None:
    """mock 拦截下请求发往 /chat/completions 且带 Authorization，返回 content。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "这是答案"}}]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = DeepSeekClient(
            api_key="test-key",
            model="deepseek-chat",
            client=http,
        )
        text = await client.generate([{"role": "user", "content": "你好"}])

    assert text == "这是答案"
