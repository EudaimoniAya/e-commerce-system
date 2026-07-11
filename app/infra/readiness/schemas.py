"""readiness 模块响应模型。"""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "unavailable", "skipped"]
ReadinessStatus = Literal["ready", "not_ready"]


class ReadinessResponse(BaseModel):
    """聚合 readiness 探针响应体。"""

    status: ReadinessStatus
    checks: dict[str, CheckStatus]
