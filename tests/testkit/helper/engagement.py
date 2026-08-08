"""engagement 域 HTTP helper（原子单次 HTTP，返回 ``*Result``，不 assert 成功）。"""

from httpx import AsyncClient, Response

from tests.testkit.results import (
    BatchDeleteFavoritesResult,
    BrowseAcceptedResult,
    BrowseListResult,
    FavoriteListResult,
    FavoriteResult,
)


async def add_favorite(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_id: str,
) -> FavoriteResult:
    """调用 POST /favorites，返回 FavoriteResult（不 assert 成功状态码）。

    body ``{"product_id": "<uuid>"}``。首次收藏 201，重复收藏 200（幂等）。
    """
    response: Response = await client.post(
        "/favorites",
        json={"product_id": product_id},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return FavoriteResult(status_code=response.status_code, body=body)


async def delete_favorite(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_id: str,
) -> FavoriteResult:
    """调用 DELETE /favorites/{product_id}，返回 FavoriteResult（status_code 204 时 body 为 None）。"""
    response: Response = await client.delete(
        f"/favorites/{product_id}",
        headers=headers,
    )
    return FavoriteResult(status_code=response.status_code, body=None)


async def list_favorites(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    limit: int | None = None,
    offset: int | None = None,
) -> FavoriteListResult:
    """调用 GET /favorites，返回 FavoriteListResult（不 assert 成功状态码）。

    ``limit``/``offset`` 省略时由服务端默认（20 / 0）。
    """
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    response: Response = await client.get(
        "/favorites",
        params=params,
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return FavoriteListResult(status_code=response.status_code, body=body)


async def batch_delete_favorites(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_ids: list[str],
) -> BatchDeleteFavoritesResult:
    """调用 POST /favorites/batch-delete，返回 BatchDeleteFavoritesResult。

    body ``{"product_ids": ["<uuid>", ...]}``；删除当前用户收藏中与列表匹配的项。
    """
    response: Response = await client.post(
        "/favorites/batch-delete",
        json={"product_ids": product_ids},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return BatchDeleteFavoritesResult(status_code=response.status_code, body=body)


# ── 浏览（user_browse_history）────────────────────────────────


async def record_browse(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_id: str,
) -> BrowseAcceptedResult:
    """调用 POST /browse，返回 BrowseAcceptedResult（不 assert 成功状态码）。

    body ``{"product_id": "<uuid>"}``。校验通过返回 202 ``{"accepted": true}``；
    catalog 中不存在返回 422。

    BackgroundTasks 契约：``httpx.ASGITransport`` 会 await 完整 ASGI app 生命周期
    （含响应发送后的 BackgroundTasks），因此本 helper 返回时后台 upsert 已完成，
    Case 可直接 assert DB 状态（无需额外 flush fixture）。
    """
    response: Response = await client.post(
        "/browse",
        json={"product_id": product_id},
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return BrowseAcceptedResult(status_code=response.status_code, body=body)


async def list_browse(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    limit: int | None = None,
    offset: int | None = None,
) -> BrowseListResult:
    """调用 GET /browse，返回 BrowseListResult（不 assert 成功状态码）。

    ``limit``/``offset`` 省略时由服务端默认（20 / 0）。
    """
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    response: Response = await client.get(
        "/browse",
        params=params,
        headers=headers,
    )
    body = None
    if 200 <= response.status_code < 300 and response.content:
        body = response.json()
    return BrowseListResult(status_code=response.status_code, body=body)


async def delete_browse(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    product_id: str,
) -> BrowseAcceptedResult:
    """调用 DELETE /browse/{product_id}，返回 BrowseAcceptedResult（status_code 204 时 body 为 None）。"""
    response: Response = await client.delete(
        f"/browse/{product_id}",
        headers=headers,
    )
    return BrowseAcceptedResult(status_code=response.status_code, body=None)
