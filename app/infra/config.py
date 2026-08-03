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


@lru_cache
def get_settings() -> Settings:
    """返回缓存的配置单例。"""
    return Settings()
