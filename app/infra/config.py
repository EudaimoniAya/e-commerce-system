"""应用配置（12-factor 环境变量注入）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量加载的运行时配置。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_env: str = "development"


@lru_cache
def get_settings() -> Settings:
    """返回缓存的配置单例。"""
    return Settings()
