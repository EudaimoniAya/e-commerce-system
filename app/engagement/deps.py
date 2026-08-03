"""engagement 域 FastAPI 依赖。"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.deps import get_shop_service
from app.catalog.service import ShopService
from app.engagement.repository import BrowseRepository, FavoriteRepository
from app.engagement.service import BrowseService, FavoriteService
from app.infra.database import get_db


def get_favorite_repository(
    session: AsyncSession = Depends(get_db),
) -> FavoriteRepository:
    """注入收藏仓储。"""
    return FavoriteRepository(session)


def get_favorite_service(
    session: AsyncSession = Depends(get_db),
    favorite_repo: FavoriteRepository = Depends(get_favorite_repository),
    catalog_service: ShopService = Depends(get_shop_service),
) -> FavoriteService:
    """注入收藏编排服务（共享同一 DB 事务；跨域依赖 catalog service）。"""
    return FavoriteService(session, favorite_repo, catalog_service)


def get_browse_repository(
    session: AsyncSession = Depends(get_db),
) -> BrowseRepository:
    """注入浏览仓储。"""
    return BrowseRepository(session)


def get_browse_service(
    session: AsyncSession = Depends(get_db),
    browse_repo: BrowseRepository = Depends(get_browse_repository),
    catalog_service: ShopService = Depends(get_shop_service),
) -> BrowseService:
    """注入浏览编排服务（共享同一 DB 事务；跨域依赖 catalog service）。"""
    return BrowseService(session, browse_repo, catalog_service)
