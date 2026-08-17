"""readiness HTTP 路由。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import app.infra.readiness.service as readiness_service
from app.infra.readiness.schemas import ReadinessResponse

router = APIRouter(tags=["readiness"])


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check() -> JSONResponse:
    """聚合 readiness 探针，检查 MySQL、Redis 与 PostgreSQL（AI 读库）连通性。"""
    mysql_ok = readiness_service.is_mysql_ready()
    redis_ok = readiness_service.is_redis_ready()
    postgresql_ok = readiness_service.is_postgresql_ready()
    ready = mysql_ok and redis_ok and postgresql_ok
    body = ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks={
            "mysql": "ok" if mysql_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
            "postgresql": "ok" if postgresql_ok else "unavailable",
        },
    )
    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())
