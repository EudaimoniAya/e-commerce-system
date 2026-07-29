"""health 模块响应模型。"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """存活探针响应体。"""

    status: str
