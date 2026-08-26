"""LLM 客户端：``LLMClient`` 协议、``FakeLLMClient``（CI/默认）与 ``DeepSeekClient``。

与 Embedder 同构但放 **ai 域**（仅客服 agent 使用，infra 不膨胀）。pytest/CI
固定 ``LLM_PROVIDER=mock``，不打真实 DeepSeek HTTP；DeepSeek 由 dev 手验。
"""

from __future__ import annotations

import json
from typing import Protocol

import httpx

_DEFAULT_TIMEOUT_SECONDS = 60.0


class LLMClient(Protocol):
    """LLM 提供者协议：``generate(messages) -> str``。"""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """将对话消息发送给 LLM，返回正文文本。"""


class FakeLLMClient:
    """可编程输出：``str`` 原样返回；``dict``/``list`` 序列化为 JSON（供 NL 网关解析）。

    CI 与默认测试使用；不访问网络。
    """

    def __init__(self, output: str | dict | list | None = None) -> None:
        self._output = output
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if self._output is None:
            return ""
        if isinstance(self._output, str):
            return self._output
        return json.dumps(self._output, ensure_ascii=False)


class DeepSeekClient:
    """DeepSeek（OpenAI 兼容）``/chat/completions`` HTTP 客户端。

    ``client`` 可注入（测试传 ``httpx.MockTransport`` 的 AsyncClient）；缺省自建。
    HTTP 失败经 ``raise_for_status`` fail-fast，不静默兜底。
    """

    _CHAT_COMPLETIONS_PATH = "/chat/completions"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT_SECONDS)
        )

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """POST chat/completions，返回 ``choices[0].message.content``。"""
        response = await self._client.post(
            f"{self._base_url}{self._CHAT_COMPLETIONS_PATH}",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "messages": messages},
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
