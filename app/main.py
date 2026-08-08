"""FastAPI 应用入口 — create_app 工厂 + 模块级 app 单例。"""

from fastapi import FastAPI

from app.catalog.router import router as catalog_router
from app.engagement.router import router as engagement_router
from app.infra.config import get_settings
from app.infra.errors.register import register_exception_handlers
from app.infra.health.router import router as health_router
from app.infra.logging.middleware import RequestIDMiddleware
from app.infra.logging.setup import setup_logging
from app.infra.readiness.router import router as readiness_router
from app.media.router import router as media_router
from app.ordering.cart_router import router as cart_router
from app.ordering.router import router as ordering_router
from app.support.router import router as support_router
from app.user.router import router as user_router


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    组装顺序：
    1. setup_logging（按 Settings.app_env 推导 loguru sink）
    2. request_id middleware（X-Request-ID 透传/生成 + logger.contextualize）
    3. exception handlers（统一 error JSON 契约）
    4. 挂载各业务域路由
    """
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(title="e-commerce-system")

    # request_id middleware（纯 ASGI 避免 BaseHTTPMiddleware ContextVar 丢失）
    app.add_middleware(RequestIDMiddleware)

    # exception handlers（覆盖 FastAPI 默认 detail 响应为统一 error JSON）
    register_exception_handlers(app)

    # 路由
    app.include_router(health_router)
    app.include_router(readiness_router)
    app.include_router(user_router)
    app.include_router(catalog_router)
    app.include_router(cart_router)
    app.include_router(ordering_router)
    app.include_router(engagement_router)
    app.include_router(support_router)
    app.include_router(media_router)

    return app


# 模块级 app 单例（uvicorn 入口与 conftest 均通过此符号访问）
app = create_app()
