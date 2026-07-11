"""readiness HTTP 路由。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import app.infra.readiness.service as readiness_service
from app.infra.readiness.schemas import ReadinessResponse

router = APIRouter(tags=["readiness"])


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check() -> JSONResponse:
    """聚合 readiness 探针，检查 MySQL 连通性。"""
    mysql_ok = readiness_service.is_mysql_ready()
    body = ReadinessResponse(
        status="ready" if mysql_ok else "not_ready",
        checks={"mysql": "ok" if mysql_ok else "unavailable"},
    )
    status_code = 200 if mysql_ok else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())
