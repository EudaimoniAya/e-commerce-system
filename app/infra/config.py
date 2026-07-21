"""应用配置（12-factor 环境变量注入）。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量加载的运行时配置。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_env: str = "development"
    jwt_secret_key: str = Field(min_length=32)
    jwt_issuer: str = "e-commerce-system"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # 订单预留库存超时（秒）：超出时限后懒释放 → cancelled + expired
    order_reservation_ttl_seconds: int = 86400


@lru_cache
def get_settings() -> Settings:
    """返回缓存的配置单例。"""
    return Settings()
