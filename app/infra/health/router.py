"""health HTTP 路由。"""

from fastapi import APIRouter

from app.infra.health.schemas import HealthResponse
from app.infra.health.service import get_health_status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """存活探针端点，无需认证。"""
    return get_health_status()
