"""health 业务逻辑（纯内存，无外部 IO）。"""

from app.infra.health.schemas import HealthResponse


def get_health_status() -> HealthResponse:
    """返回服务存活状态。"""
    return HealthResponse(status="ok")
