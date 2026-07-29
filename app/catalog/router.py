"""catalog 域 HTTP 路由（类目、商品、店铺）。"""

import uuid

from fastapi import APIRouter, Depends, status

from app.catalog.deps import get_current_shop, get_shop_service
from app.catalog.models import Shop
from app.catalog.schemas import (
    CategoryCreate,
    CategoryResponse,
    PaginatedProducts,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    ShopCreate,
    ShopResponse,
    ShopUpdate,
)
from app.catalog.service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.pagination.deps import get_pagination_params
from app.infra.pagination.schemas import PaginationParams
from app.user.deps import require_admin

router = APIRouter()


@router.get("/categories", response_model=list[CategoryResponse], tags=["categories"])
async def list_categories(
    service: ShopService = Depends(get_shop_service),
) -> list[CategoryResponse]:
    """公开返回扁平类目列表。"""
    return await service.list_categories()


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["categories"],
)
async def create_category(
    body: CategoryCreate,
    _admin_id: uuid.UUID = Depends(require_admin),
    service: ShopService = Depends(get_shop_service),
) -> CategoryResponse:
    """管理员创建类目。"""
    return await service.create_category(body)


@router.get("/products", response_model=PaginatedProducts, tags=["products"])
async def list_public_products(
    category_id: uuid.UUID | None = None,
    params: PaginationParams = Depends(get_pagination_params),
    service: ShopService = Depends(get_shop_service),
) -> PaginatedProducts:
    """公开分页返回已上架且店铺 active 的商品。"""
    return await service.list_public_products(
        category_id=category_id,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/products/{product_id}", response_model=ProductResponse, tags=["products"])
async def read_public_product(
    product_id: uuid.UUID,
    service: ShopService = Depends(get_shop_service),
) -> ProductResponse:
    """公开查询商品详情。"""
    return await service.get_public_product(product_id)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
)
async def create_product(
    body: ProductCreate,
    shop: Shop = Depends(get_current_shop),
    service: ShopService = Depends(get_shop_service),
) -> ProductResponse:
    """店主在 active 店铺下创建商品。"""
    return await service.create_product(shop, body)


@router.patch("/products/{product_id}", response_model=ProductResponse, tags=["products"])
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ShopService = Depends(get_shop_service),
) -> ProductResponse:
    """店主更新本店商品。"""
    return await service.update_product(product_id, user_id, body)


@router.post(
    "/shops",
    response_model=ShopResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["shops"],
)
async def create_shop(
    body: ShopCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """已认证用户创建店铺。"""
    return await service.create_shop(user_id, body)


@router.get("/shops/me", response_model=ShopResponse, tags=["shops"])
async def read_my_shop(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """返回当前用户作为店主的店铺。"""
    return await service.get_my_shop(user_id)


@router.get(
    "/shops/me/products",
    response_model=PaginatedProducts,
    tags=["products"],
)
async def list_my_products(
    params: PaginationParams = Depends(get_pagination_params),
    shop: Shop = Depends(get_current_shop),
    service: ShopService = Depends(get_shop_service),
) -> PaginatedProducts:
    """店主分页返回本店全部商品（含未上架）。"""
    return await service.list_my_products(shop, limit=params.limit, offset=params.offset)


@router.patch("/shops/me", response_model=ShopResponse, tags=["shops"])
async def update_my_shop(
    body: ShopUpdate,
    shop: Shop = Depends(get_current_shop),
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """店主更新自己的店铺。"""
    return await service.update_my_shop(shop, body)


@router.get("/shops/{shop_id}", response_model=ShopResponse, tags=["shops"])
async def read_public_shop(
    shop_id: uuid.UUID,
    service: ShopService = Depends(get_shop_service),
) -> ShopResponse:
    """公开查询店铺详情。"""
    return await service.get_public_shop(shop_id)
