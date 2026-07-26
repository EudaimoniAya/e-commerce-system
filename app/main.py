"""FastAPI 应用入口 — create_app 工厂 + 模块级 app 单例。"""

from fastapi import FastAPI

from app.catalog.router import router as catalog_router
from app.infra.config import get_settings
from app.infra.health.router import router as health_router
from app.infra.logging.middleware import request_id_middleware
from app.infra.logging.setup import setup_logging
from app.infra.readiness.router import router as readiness_router
from app.ordering.router import router as ordering_router
from app.user.router import router as user_router


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    组装顺序：
    1. setup_logging（按 Settings.app_env 推导 loguru sink）
    2. request_id middleware（X-Request-ID 透传/生成 + logger.contextualize）
    3. 挂载各业务域路由
    4. 暂不注册 exception handlers（Task 2.3）
    """
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(title="e-commerce-system")

    # request_id middleware（应在路由之前注册，使 200 路径日志也含 request_id）
    app.middleware("http")(request_id_middleware)

    # 路由
    app.include_router(health_router)
    app.include_router(readiness_router)
    app.include_router(user_router)
    app.include_router(catalog_router)
    app.include_router(ordering_router)

    return app


# 模块级 app 单例（uvicorn 入口与 conftest 均通过此符号访问）
app = create_app()
