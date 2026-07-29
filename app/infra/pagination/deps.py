"""infra 分页 FastAPI 依赖。

提供 ``get_pagination_params`` —— 唯一的分页 Query 解析入口。
"""

from typing import Annotated

from fastapi import Query

from app.infra.pagination.schemas import PaginationParams

DEFAULT_PAGE_LIMIT = 20  # 分页默认每页条数。
MAX_PAGE_LIMIT = 100  # 分页最大每页条数（超出返回 422）。


LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]
OffsetQuery = Annotated[int, Query(ge=0)]


def get_pagination_params(
    limit: LimitQuery = DEFAULT_PAGE_LIMIT,
    offset: OffsetQuery = 0,
) -> PaginationParams:
    """FastAPI 分页参数依赖。

    Returns:
        ``PaginationParams``（Pydantic BaseModel，**非** tuple）。
    """
    return PaginationParams(limit=limit, offset=offset)
