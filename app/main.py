"""FastAPI 应用入口。"""

from fastapi import FastAPI

from app.infra.health.router import router as health_router

app = FastAPI(title="e-commerce-system")
app.include_router(health_router)
