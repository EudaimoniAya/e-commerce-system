"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app.catalog.router import router as catalog_router
from app.infra.health.router import router as health_router
from app.infra.readiness.router import router as readiness_router
from app.ordering.router import router as ordering_router
from app.user.router import router as user_router

app = FastAPI(title="e-commerce-system")
app.include_router(health_router)
app.include_router(readiness_router)
app.include_router(user_router)
app.include_router(catalog_router)
app.include_router(ordering_router)
