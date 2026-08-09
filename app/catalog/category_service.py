"""catalog 域类目业务逻辑（CategoryService）。"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.catalog.models import Category
from app.catalog.repository import CategoryRepository
from app.catalog.schemas import CategoryCreate, CategoryResponse

_CATEGORY_DUPLICATE_MSG = "Category name already exists under this parent"
_CATEGORY_PARENT_NOT_FOUND_MSG = "Parent category not found"


def _to_category_response(category: Category) -> CategoryResponse:
    """ORM 类目转对外 DTO。"""
    return CategoryResponse(
        id=str(category.id),
        parent_id=str(category.parent_id) if category.parent_id is not None else None,
        name=category.name,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


class CategoryService:
    """catalog 域类目业务服务（仅 category repo；无 media）。"""

    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    async def create_category(self, data: CategoryCreate) -> CategoryResponse:
        """管理员创建类目。"""
        parent_id: uuid.UUID | None = None
        if data.parent_id is not None:
            parent_id = uuid.UUID(data.parent_id)
            parent = await self._repository.get_by_id(parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_CATEGORY_PARENT_NOT_FOUND_MSG,
                )

        duplicate = await self._repository.get_by_parent_and_name(parent_id, data.name)
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CATEGORY_DUPLICATE_MSG,
            )

        try:
            category = await self._repository.create(
                category_id=uuid.uuid4(),
                name=data.name,
                parent_id=parent_id,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_CATEGORY_DUPLICATE_MSG,
            ) from exc
        return _to_category_response(category)

    async def list_categories(self) -> list[CategoryResponse]:
        """返回扁平类目列表。"""
        categories = await self._repository.list_all()
        return [_to_category_response(item) for item in categories]
