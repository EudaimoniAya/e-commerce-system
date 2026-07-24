"""测试环境 bootstrap：加载 .env.test 并确保 Settings 缓存正确。

§1（APP_ENV_FILE + .env.test）完成后，测试环境变量由 ``.env.test`` +
``APP_ENV_FILE`` 提供，不再需要 conftest/helper 内的 os.environ 覆盖。

纪律
----
- ``get_settings.cache_clear()`` **仅允许**在此模块的 ``bootstrap_test_env()`` 中调用。
- HTTP helper 与 atomic orchestrator 不得调用 ``cache_clear``。
- 极少数 mutating fixture teardown 如须清缓存，应通过 ``bootstrap_test_env()`` 而非直接调
  ``cache_clear``。
"""

import os

from app.infra.config import get_settings


def bootstrap_test_env() -> None:
    """在 import app 之前调用，确保 Settings 从 ``.env.test`` 加载。

    - 如果 ``APP_ENV_FILE`` 未设置，fallback 到 ``.env.test``。
    - 清空 ``get_settings`` 的 ``lru_cache``，使首次 import 时读取正确的 env 文件。
    - 测试过程中 Settings 不会再变（会话级稳定），此后再无需 ``cache_clear``。

    **这是测试代码中调用 ``get_settings.cache_clear()`` 的唯一合法地点。**
    """
    os.environ.setdefault("APP_ENV_FILE", ".env.test")
    get_settings.cache_clear()
