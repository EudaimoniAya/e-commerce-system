"""AI 域组合根：仅装配类（无 router / 无 get_current_*）。

CLI 与测试以普通函数调用；将来若有 AI HTTP，同一函数可挂 ``Depends``。
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import DeepSeekClient, LLMClient, MockLLMClient
from app.ai.prompts.loader import PromptLoader
from app.infra.config import get_settings
from app.media.deps import get_media_service, get_storage_backend
from app.media.service import MediaService


def build_media_service(session: AsyncSession) -> MediaService:
    """装配 MediaService：经 media 域 service-provider + storage backend。"""
    return get_media_service(
        session=session,
        storage=get_storage_backend(get_settings()),
    )


def build_llm_client() -> LLMClient:
    """按 Settings 构造 LLM 客户端：mock（CI/默认）| deepseek（dev 手验）。"""
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockLLMClient()
    if settings.llm_provider == "deepseek":
        return DeepSeekClient(
            api_key=settings.llm_api_key or "",
            model=settings.llm_model,
            base_url=settings.llm_base_url,
        )
    raise ValueError(f"不支持的 llm_provider: {settings.llm_provider}")


def build_prompt_loader() -> PromptLoader:
    """构造指向 ``app/ai/prompts/`` 的提示词加载器。"""
    return PromptLoader(base_dir=Path(__file__).parent / "prompts")
