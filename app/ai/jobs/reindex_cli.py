"""ai 域 reindex 命令行入口（供 ``task ai:reindex-*`` 调用，design D8）。

用法::

    python -m app.ai.jobs.reindex_cli shop --shop-id <uuid>
    python -m app.ai.jobs.reindex_cli product --product-id <uuid>
    python -m app.ai.jobs.reindex_cli document --source-kind catalog_text --document-id <uuid>

- ``shop``：整店双源重建（catalog_text + media_document）+ orphan 清理
  （下架商品 / 已删附件的遗留 chunk 一并清除，Task 7.4）。
- ``product``：单商品全部 document 重建。
- ``document``：单文档重建（``document_id`` 命名空间由 ``source_kind`` 消歧，design D5）。

注意：命令对 **dev 库**（``.env`` 的 ``DATABASE_URL`` / ``AI_DATABASE_URL``）执行；
功能验证请走 integration 测试，勿用 CLI 操作测试库。
"""

import argparse
import asyncio
import uuid

from app.ai.deps import build_media_service
from app.ai.rag.indexing.service import (
    reindex_document,
    reindex_product,
    reindex_shop,
)
from app.ai.rag.schemas import SOURCE_KIND_CHOICES, ReindexStats
from app.infra.database import get_session_factory


def _build_parser() -> argparse.ArgumentParser:
    """构造子命令解析器（shop / product / document）。"""
    parser = argparse.ArgumentParser(
        prog="ai:reindex",
        description="RAG 语料重建（per document delete-then-insert；shop 含 orphan 清理）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shop_parser = subparsers.add_parser("shop", help="整店双源重建（含 orphan 扫描）")
    shop_parser.add_argument("--shop-id", type=uuid.UUID, required=True)

    product_parser = subparsers.add_parser("product", help="重建单商品全部文档")
    product_parser.add_argument("--product-id", type=uuid.UUID, required=True)

    document_parser = subparsers.add_parser("document", help="重建单文档")
    document_parser.add_argument(
        "--source-kind",
        required=True,
        choices=SOURCE_KIND_CHOICES,
        help="document_id 命名空间消歧：catalog_text=product_id；media_document=附件 UUID",
    )
    document_parser.add_argument("--document-id", type=uuid.UUID, required=True)

    return parser


async def _run(args: argparse.Namespace) -> ReindexStats:
    """以独立 MySQL session 执行对应 reindex（PG 侧由 reindex 内部经 AI session 写入）。"""
    async with get_session_factory()() as session:
        media_service = build_media_service(session)
        if args.command == "shop":
            return await reindex_shop(
                shop_id=str(args.shop_id),
                db_session=session,
                media_service=media_service,
            )
        if args.command == "product":
            return await reindex_product(
                product_id=str(args.product_id),
                db_session=session,
                media_service=media_service,
            )
        return await reindex_document(
            source_kind=args.source_kind,
            document_id=str(args.document_id),
            db_session=session,
            media_service=media_service,
        )


def _print_stats(stats: ReindexStats) -> None:
    """打印 reindex 统计（errors 逐条列出，便于定位 skipped 原因）。"""
    print(
        f"documents_processed={stats.documents_processed}  "
        f"chunks_inserted={stats.chunks_inserted}  "
        f"documents_skipped={stats.documents_skipped}  "
        f"errors={len(stats.errors)}"
    )
    for error in stats.errors:
        print(f"  ! {error}")


def main() -> None:
    """CLI 入口。"""
    args = _build_parser().parse_args()
    stats = asyncio.run(_run(args))
    _print_stats(stats)


if __name__ == "__main__":
    main()
