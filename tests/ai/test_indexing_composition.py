"""AI 组合根与砍门面契约测试（TDD 红：deps / 删门面尚未实现）。

覆盖 spec ai-domain-composition / ai-rag-indexing：
- reindex_* 的 media_service 必传（无缺省自装配）
- reindex_product SHALL NOT 调用 list_products_for_rag_indexing(shop_id=None)
- SHALL NOT 存在 app.ai.service 门面
- CLI _run 经 app.ai.deps.build_media_service 装配后传入
"""

import inspect
import uuid
from unittest.mock import AsyncMock, patch

import allure
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@allure.epic("ai")
@allure.feature("composition")
@allure.title("reindex_* 的 media_service 必传、无缺省")
def test_reindex_requires_media_service() -> None:
    """indexing 三个入口的 media_service 不得有默认值（禁止 service 自装配）。"""
    from app.ai.rag.indexing.service import (
        reindex_document,
        reindex_product,
        reindex_shop,
    )

    for func in (reindex_product, reindex_shop, reindex_document):
        param = inspect.signature(func).parameters["media_service"]
        assert param.default is inspect.Parameter.empty, func.__name__


@allure.epic("ai")
@allure.feature("composition")
@allure.title("不存在 app.ai.service 门面模块")
def test_ai_service_facade_module_removed() -> None:
    """检索入口只留 retrieval.service；门面文件 SHALL NOT 存在。"""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.ai.service")


@allure.epic("ai")
@allure.feature("composition")
@allure.title("CLI _run 经 deps.build_media_service 装配")
def test_reindex_cli_assembles_media_via_deps() -> None:
    """CLI 不得在 service 内自装配，须引用 app.ai.deps.build_media_service。"""
    from app.ai.jobs import reindex_cli

    source = inspect.getsource(reindex_cli)
    assert "build_media_service" in source
    assert "app.ai.deps" in source


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("indexing")
@allure.title("reindex_product 不调用 list_products_for_rag_indexing(shop_id=None)")
async def test_reindex_product_does_not_list_all_platform(
    db_session: AsyncSession,
    clean_ai_chunks: None,
    stub_media_service: AsyncMock,
) -> None:
    """单商品重建禁止全平台 list；应走 get_product_for_rag_indexing。"""
    from app.ai.rag.indexing.service import reindex_product

    with patch(
        "app.ai.rag.indexing.service.list_products_for_rag_indexing",
        new_callable=AsyncMock,
    ) as listed:
        listed.return_value = []
        await reindex_product(
            product_id=str(uuid.uuid4()),
            db_session=db_session,
            media_service=stub_media_service,
        )

    for call in listed.await_args_list:
        shop_id = call.kwargs.get("shop_id")
        if shop_id is None and call.args:
            shop_id = call.args[0]
        assert shop_id is not None
