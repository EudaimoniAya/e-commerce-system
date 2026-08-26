"""应用配置（12-factor 环境变量注入）。"""

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.environ.get("APP_ENV_FILE", ".env")


class Settings(BaseSettings):
    """从环境变量加载的运行时配置。"""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str
    redis_url: str
    app_env: str = "development"
    jwt_secret_key: str = Field(min_length=32)
    jwt_issuer: str = "e-commerce-system"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # 订单预留库存超时（秒）：超出时限后懒释放 → cancelled + expired
    order_reservation_ttl_seconds: int = 86400

    # SMS OTP
    sms_otp_ttl_seconds: int = 300
    sms_daily_send_limit: int = 10
    sms_verify_fail_limit: int = 5
    sms_verify_fail_window_seconds: int = 900
    sms_otp_fixed_code: str | None = None

    # engagement 浏览记录（user_browse_history）：top N + retention + debounce
    browse_history_max_per_user: int = 50
    browse_history_retention_days: int = 30
    browse_debounce_seconds: int = 5

    # ── media 平台域 ─────────────────────────────────────────────────
    # storage backend：local（落盘 .data/media）| memory（进程内，测试用）
    media_storage_backend: str = "local"
    # 本地存储根目录（仅 local backend 生效）
    media_storage_root: str = ".data/media"
    # 上传文件大小上限（字节），默认 5 MB
    media_max_size_bytes: int = 5_242_880
    # 每用户每窗口最多上传次数（Redis 滑动窗口限速）
    media_upload_rate_limit_per_minute: int = 60

    # ── AI 读库（PostgreSQL + pgvector）────────────────────────────
    ai_database_url: str
    embedding_provider: str  # mock | zhipu | dashscope
    embedding_model: str
    embedding_dimension: int  # 须显式配置，无 default
    embedding_api_key: str | None = None

    # ── AI 客服：LLM 与 τ 门禁 ────────────────────────────────
    # LLM provider：mock（CI / 默认测试）| deepseek（dev 手验）；对话模型与 embedding 厂商可分离
    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    llm_api_key: str | None = None
    # OpenAI 兼容 base URL（deepseek 默认）
    llm_base_url: str = "https://api.deepseek.com"
    # τ 最小门禁阈值（[0,1]；低于则拒答转人工）。本刀仅 NLU 置信度一个分数源
    tau_threshold: float = 0.3

    # RAG chunking：单 chunk 最大字符数（catalog_text 短文本 / media_document 段落切分）
    rag_chunk_max_chars: int = 800


@lru_cache
def get_settings() -> Settings:
    """返回缓存的配置单例。"""
    return Settings()


def reject_mock_providers_in_production(settings: Settings) -> None:
    """生产环境禁止以 mock 假实现启动 llm / embedding（fail-fast）。

    ``APP_ENV=production`` 时 ``LLM_PROVIDER`` / ``EMBEDDING_PROVIDER`` 选 ``mock``
    即抛错，避免静默用假实现；``development`` / ``test`` 不拦（pytest / CI 仍用
    mock）。短信假发送类（``FakeSmsProvider``）无配置开关，不参与本门禁。
    """
    if settings.app_env != "production":
        return
    if settings.llm_provider == "mock":
        raise ValueError(
            "production 环境不得使用 LLM_PROVIDER=mock（请配置真实厂商 deepseek）"
        )
    if settings.embedding_provider == "mock":
        raise ValueError(
            "production 环境不得使用 EMBEDDING_PROVIDER=mock"
            "（请配置真实厂商 zhipu / dashscope）"
        )
