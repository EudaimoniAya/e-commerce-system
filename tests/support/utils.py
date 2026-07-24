"""tests/support 纯函数工具：请求头投影 + 测试环境 bootstrap。

无 HTTP/DB 依赖，不 import 任何业务域模块。

纪律
----
- ``get_settings.cache_clear()`` **仅允许**在此模块的 ``bootstrap_test_env()`` 中调用。
- HTTP helper 与 atomic orchestrator 不得调用 ``cache_clear``。
- 极少数 mutating fixture teardown 如须清缓存，应通过 ``bootstrap_test_env()`` 而非直接调
  ``cache_clear``。
"""

import os

from app.infra.config import get_settings


# ── bearer 请求头投影 ──────────────────────────────────────────

def bearer_headers(access_token: str) -> dict[str, str]:
    """从 access_token 字符串投影 Bearer Authorization 请求头。"""
    return {"Authorization": f"Bearer {access_token}"}


# ── 测试环境 bootstrap ─────────────────────────────────────────

def bootstrap_test_env() -> None:
    """在 import app 之前调用，确保 Settings 从 ``.env.test`` 加载。

    - 如果 ``APP_ENV_FILE`` 未设置，fallback 到 ``.env.test``。
    - 清空 ``get_settings`` 的 ``lru_cache``，使首次 import 时读取正确的 env 文件。
    - 测试过程中 Settings 不会再变（会话级稳定），此后再无需 ``cache_clear``。

    **这是测试代码中调用 ``get_settings.cache_clear()`` 的唯一合法地点。**
    """
    os.environ.setdefault("APP_ENV_FILE", ".env.test")
    get_settings.cache_clear()
