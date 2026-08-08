"""infra 分页 Pydantic 模型。

- ``PaginationParams``：Router 层入参（Pydantic BaseModel，**禁止** tuple）
- ``Paginated[TResponse]``：泛型分页响应壳（items / total / limit / offset）
"""

from pydantic import BaseModel


class PaginationParams(BaseModel):
    """分页入参（经 FastAPI Query 校验后由 get_pagination_params 构造）。

    Router SHALL 以 ``params.limit`` / ``params.offset`` 属性访问，
    **禁止** ``limit, offset = params`` 元组解构。
    """

    limit: int
    offset: int


class Paginated[TResponse](BaseModel):
    """泛型分页响应壳。

    字段与命名 SHALL 在所有已迁移端点间保持一致。
    ``TResponse`` 表示 ``items`` 元素为 **API Response DTO**，**不得**为 ORM。
    """

    items: list[TResponse]
    total: int
    limit: int
    offset: int
