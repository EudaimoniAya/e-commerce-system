"""独立 Eval 店种子脚本（ai-ragas-eval §4.1）：经 catalog.service 写 MySQL，再 reindex 写 PG。

契约（design 决策 2/7、tasks 4.1）：
- 经 ``catalog.service``（``ShopService`` / ``CategoryService`` / ``ProductService``）写入
  独立 Eval 店与 2–3 个可区分事实的商品；**不**直接写 catalog/media ORM
  （Shop ORM 仅经 ``ShopRepository.get_by_owner_user_id`` 读回，作为 service 入参；
   店主用户属 user 域，直接建行不违反本刀「禁 catalog/media ORM」）；
- 商品说明书经 ``media.service``（``MediaService.upload``）上传并关联商品，产出
  ``source_kind=media_document`` 语料（第二检索路径）；
- 再走已有 ``reindex_shop``（组合根经 ``app.ai.deps.build_media_service``）写 PG；
- 目标 **dev** 库（``.env`` 的 ``DATABASE_URL`` / ``AI_DATABASE_URL``）；
  本店语料与黄金测试集冻结同一快照，勿与 pytest 随建随清的 ``clean_ai_chunks`` 店混用。

用法::

    devbox run -- uv run python -m evals.seed_eval_shop            # 首次种子
    devbox run -- uv run python -m evals.seed_eval_shop --reset    # 删除本 Eval 店数据后重建

输出 shop_id / product_ids / manual_asset_id / chunk 明细，供 ``evals/golden/<snapshot_id>/``
的 manifest 与 samples.jsonl 引用（reference_context_ids = ``document_id:chunk_index``）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.ai.deps import build_media_service
from app.ai.rag.indexing.service import reindex_shop
from app.ai.rag.schemas import ReindexStats
from app.catalog.category_service import CategoryService
from app.catalog.product_service import ProductService
from app.catalog.repository import (
    CategoryRepository,
    ProductRepository,
    ShopRepository,
)
from app.catalog.schemas import CategoryCreate, ProductCreate, ShopCreate
from app.catalog.shop_service import ShopService
from app.infra.config import get_settings
from app.infra.database import get_session_factory
from app.media.service import MediaService
from app.user.models import User

# ── git 剧本：Eval 店与商品定义（可复现种子）─────────────────────────────

SEED_ID = "eval-drinkware-shop"
SHOP_NAME = "鲜食评测铺"
SHOP_DESCRIPTION = (
    "离线 RAGAS 评测专用独立店铺；语料与黄金测试集同快照，勿用于功能验收。"
)
OWNER_NICKNAME = "eval_shop_owner"
CATEGORY_NAME = "评测商品"
MANUAL_PRODUCT_NAME = "智能温湿度计 墨水屏"


@dataclass(frozen=True)
class ProductSpec:
    """一个商品的语料剧本（name/description 即 catalog_text 源）。"""

    name: str
    price: str
    stock: int
    description: str


# 长描述刻意超过 RAG_CHUNK_MAX_CHARS(800) 以产出多 chunk（跨 chunk 召回样本）；
# 手册（media_document）走按段落切分，与 catalog_text 路径互补。
PRODUCTS: tuple[ProductSpec, ...] = (
    ProductSpec(
        name="冷萃咖啡浓缩液 12 瓶装",
        price="88.00",
        stock=50,
        description=(
            "冷萃咖啡浓缩液，12 瓶装，每瓶 50ml，共 600ml，适合居家办公囤货。"
            "采用云南保山产阿拉比卡豆，经冷水低温浸泡 18 小时萃取，"
            "口感顺滑，风味以坚果、黑巧克力为主，尾韵带焦糖甜感，几乎没有酸涩感。"
            "每 50ml 一瓶约含咖啡因 150mg，相当于一杯标准美式的浓度，"
            "直接兑水、牛奶或气泡水即可饮用，建议浓缩液与液体比例 1:3。"
            "开封前常温阴凉处避光保存可放 7 天，开封后务必冷藏，冷藏条件下可保存 14 天。"
            "整箱未开封保质期 180 天，生产日期见瓶盖喷码。"
            "本产品不添加糖与植脂末，喜欢偏甜口感可自行加糖。"
            "快递运输全程冷链，收到后请尽快放入冰箱冷藏室。"
            "冲泡指南：1. 冰美式：浓缩液 1 份加冰水 3 份与适量冰块；"
            "2. 拿铁：浓缩液 1 份加冷藏牛奶 3 份；"
            "3. 气泡冷萃：浓缩液 1 份加气泡水 3 份，风味更清爽；"
            "4. 直接饮用：喜欢浓醇口感可按 1:2 稀释。"
            "常见问题：1. 冷萃与热萃的区别？冷萃用冷水低温长时间萃取，酸涩感更低、口感更顺滑。"
            "2. 可以加糖吗？本产品不含糖，可按喜好自行添加糖或蜂蜜。"
            "3. 一瓶能冲几杯？按 1:3 稀释，一瓶 50ml 约可冲 200ml 饮品，整箱约可冲 2.4L。"
            "4. 适合什么时候喝？早晨或午后均可，冷藏后直接饮用风味更佳。"
            "5. 孕妇可以喝吗？含咖啡因，孕妇及对咖啡因敏感人群建议谨慎饮用。"
            "6. 可以用于烹饪吗？浓缩液可直接用于制作提拉米苏、咖啡冰激凌等甜品。"
            "7. 运输损坏怎么办？全程冷链加缓冲包装，收到如发现漏液请第一时间联系客服。"
            "8. 咖啡因敏感者建议摄入量？每天建议不超过 2 瓶。"
            "原料与工艺：选用云南保山海拔 1400 米以上高山阿拉比卡豆，日晒水洗混合处理，"
            "中浅度烘焙后研磨，再以冷水低温浸泡 18 小时萃取，经冷萃设备低温过滤，"
            "保留咖啡油脂与香气，无人工香精与防腐剂。"
            "产品规格：净含量 600ml 共 12 瓶，每瓶 50ml；储存条件冷藏 2-8℃；"
            "产地云南保山；外箱毛重约 1.8kg。"
            "适用场景：办公室提神、居家早餐饮用、露营便携、聚会分享。"
            "更多问答：9. 放冰箱会凝固吗？不会，浓缩液不含乳脂，冷藏仍保持流动状态。"
            "10. 兑水比例可以调整吗？可以，按口味在 1:2 至 1:4 之间调整。"
            "11. 一瓶开封后多久喝完？建议开封后 3 天内喝完以保证风味。"
            "12. 冬季怎么喝？可兑热水制成热美式，或加热牛奶做成热拿铁。"
            "13. 冷萃与普通速溶的区别？冷萃是低温长时间萃取的浓缩液，风味更干净，"
            "不添加植脂末与糖，速溶多经高温干燥处理。"
        ),
    ),
    ProductSpec(
        name="便携保温杯 500ml 不锈钢",
        price="129.00",
        stock=30,
        description=(
            "便携保温杯，容量 500ml，杯身采用 316 不锈钢内胆，耐腐蚀不易串味。"
            "保温性能优秀：沸水倒入后 12 小时内可保持 60℃ 以上，"
            "冰饮保冷可达 24 小时，适合通勤、露营、户外运动场景。"
            "整杯重量约 280g，轻量易携带，杯盖采用一键弹盖设计并带安全锁扣，"
            "防止误触弹开。底部有硅胶防滑垫，放桌面或车内不易倾倒。"
            "杯口直径适配市面大部分车载杯架。"
            "清洗方面，杯身可放入洗碗机清洗，杯盖建议手洗以免密封圈变形。"
            "注意：不建议长时间盛装碳酸饮料或牛奶，压力与发酵可能导致胀气或异味。"
            "首次使用前建议用温水加中性清洁剂清洗内胆。"
        ),
    ),
    ProductSpec(
        name="智能温湿度计 墨水屏",
        price="59.00",
        stock=100,
        description=(
            "智能温湿度计，采用 2.9 英寸墨水屏显示，清晰省电，长时间不耗电也能常显。"
            "温度测量范围 -20℃ 至 60℃，湿度范围 0% 至 99%RH，"
            "温度精度 ±0.3℃，湿度精度 ±3%RH，满足家居与婴儿房日常监测。"
            "供电使用 2 节 AAA 电池，续航约 12 个月，无需频繁更换。"
            "支持米家 App 联动，可查看历史曲线并设置温湿度异常提醒。"
            "屏幕无背光设计，夜间需要借助外部光源查看，适合放卧室不打扰睡眠。"
            "建议摆放在室内通风处，避开阳光直射与空调出风口，以免读数偏差。"
            "机身自带支架与壁挂孔，可立在桌面或挂在墙面。"
            "本设备不带供电线，需要用户自备 AAA 电池。"
            "产品参数：显示屏 2.9 英寸墨水屏；温度量程 -20℃ 至 60℃ 精度 ±0.3℃；"
            "湿度量程 0% 至 99%RH 精度 ±3%RH；电池 2 节 AAA 续航约 12 个月；"
            "整机重量约 95g，尺寸 88mm × 88mm × 18mm。"
            "常见问题：1. 读数不准怎么办？先确认摆放位置避开阳光直射与空调出风口，"
            "静止 30 分钟后再观察。"
            "2. 可以放在室外吗？本产品为室内设计，不建议长期暴露于室外雨淋或暴晒。"
            "3. 数据会丢失吗？更换电池后设备时间与设置可能重置，历史曲线以米家 App 云端为准。"
            "4. 适合什么人群？尤其适合有宝宝的家庭监测婴儿房温湿度，也适合植物养护爱好者。"
            "5. 支持多台设备吗？同一米家账号可绑定多台本设备并分别查看。"
            "产品规格：主机尺寸 88mm × 88mm × 18mm，重量约 95g；"
            "包装内含主机、壁挂支架、说明书，不含电池；"
            "屏幕可同时显示温度、湿度、时间与电量，支持摄氏与华氏切换。"
            "适用场景：婴儿房温湿度监测、书房与办公室环境参考、植物与宠物环境照料、"
            "酒窖与雪茄房湿度参考。"
            "更多问答：6. 能同时显示温度和湿度吗？可以，墨水屏同时显示两组数值。"
            "7. 支持摄氏和华氏切换吗？支持，可在 App 或机身设置中切换。"
            "8. 读数多久刷新一次？约 10 秒刷新一次。"
            "9. 有闹钟功能吗？本产品仅作环境监测，不含闹钟功能。"
            "10. 需要安装 App 才能用吗？不需要，脱离手机也可独立显示与工作。"
        ),
    ),
)


# 商品使用说明书：经 media.service 上传为 ``media_document`` 语料（段落切分）。
MANUAL_FILENAME = "智能温湿度计使用说明书.txt"
MANUAL_CONTENT = """智能温湿度计使用说明书

【产品组成】
本产品由智能温湿度计主机、壁挂支架、两节 AAA 电池组成，出厂未预装电池。

【安装步骤】
打开背部电池盖，按正负极指示装入两节 AAA 电池；盖上电池盖后屏幕点亮显示当前温湿度。如使用壁挂，将支架固定在墙面，再把主机背孔对准支架卡扣按入即可。

【开机与米家绑定】
首次开机后 30 秒内进入配对状态。打开米家 App，点击右上角加号添加设备，按屏幕提示靠近主机并扫码完成配对。绑定成功后可在 App 查看历史曲线并设置温湿度异常提醒。

【放置与校准】
将主机放置于室内通风处，避开阳光直射与空调出风口；用于婴儿房时建议放在床头柜或尿布台，离地约 1 米。出厂已校准，如发现读数偏差明显，可长按背面校准键进入校准模式，用标准温湿度计对比校准，校准数据断电后保留。

【维护与清洁】
用干燥软布轻擦机身，请勿用水冲洗或使用腐蚀性清洁剂。长期不用时请取出电池，防止漏液损坏电路。

【保修与售后】
自签收之日起一年内，非人为损坏可凭订单号享受免费保修。保修期外提供有偿维修服务，请联系客服获取寄修地址。人为进水、跌落导致的损坏不在保修范围。

【常见问题】
1. 读数不准怎么办？先检查摆放位置，避开阳光直射与空调出风口，静止 30 分钟再观察；如仍不准请按放置与校准一节校准。2. 可以放在室外吗？本产品为室内设计，不建议长期暴露于室外雨淋或暴晒。3. 更换电池后数据会丢失吗？设备本地设置可能重置，历史曲线以米家 App 云端记录为准。4. 屏幕不亮？墨水屏本身不发光，请确认已装入电池且正负极正确。5. 支持多台设备吗？同一米家账号可绑定多台本设备并分别查看。"""


# ── 建表辅助（仅 user 域直写；catalog/media 一律经 service）────────────


async def _ensure_owner_user(session: AsyncSession) -> uuid.UUID:
    """创建（或复用）Eval 店店主，返回 owner_user_id。"""
    result = await session.execute(select(User).where(User.nickname == OWNER_NICKNAME))
    user = result.scalar_one_or_none()
    if user is not None:
        return uuid.UUID(str(user.id))
    owner = User(nickname=OWNER_NICKNAME)
    session.add(owner)
    await session.commit()
    return uuid.UUID(str(owner.id))


async def _ensure_category(session: AsyncSession) -> str:
    """创建（或复用）评测类目，返回 category_id。"""
    service = CategoryService(CategoryRepository(session))
    for category in await service.list_categories():
        if category.name == CATEGORY_NAME:
            return category.id
    return (await service.create_category(CategoryCreate(name=CATEGORY_NAME))).id


def _build_services(session: AsyncSession) -> tuple[ShopService, ProductService]:
    """按 catalog deps 的装配顺序构造 Shop/ProductService（组合根模式，不经 Depends）。"""
    media_service = build_media_service(session)
    shop_service = ShopService(ShopRepository(session), media_service)
    product_service = ProductService(
        ProductRepository(session),
        CategoryRepository(session),
        media_service,
        shop_service,
    )
    return shop_service, product_service


async def _create_shop_and_products(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    category_id: str,
) -> tuple[str, dict[str, str]]:
    """创建 Eval 店与全部剧本商品，返回 (shop_id, {product_name: product_id})。"""
    shop_service, product_service = _build_services(session)

    shop = await shop_service.create_shop(
        owner_user_id, ShopCreate(name=SHOP_NAME, description=SHOP_DESCRIPTION)
    )
    shop_id = shop.id
    shop_orm = await ShopRepository(session).get_by_id(uuid.UUID(shop_id))
    if shop_orm is None:  # pragma: no cover - 刚创建不可能不存在
        raise RuntimeError(f"shop {shop_id} 创建后读取失败")

    by_name: dict[str, str] = {}
    for spec in PRODUCTS:
        product = await product_service.create_product(
            shop_orm,
            ProductCreate(
                name=spec.name,
                price=Decimal(spec.price),
                stock=spec.stock,
                description=spec.description,
                is_published=True,
                category_ids=[category_id],
                primary_category_id=category_id,
            ),
        )
        by_name[spec.name] = product.id
    return shop_id, by_name


async def _ensure_manual(
    session: AsyncSession,
    *,
    media_service: MediaService,
    owner_user_id: uuid.UUID,
    product_id: str,
) -> str:
    """上传（或复用）商品使用说明书，返回 media_asset_id。"""
    existing = await media_service.list_documents_by_product(product_id)
    if existing:
        return existing[0].asset_id
    summary = await media_service.upload(
        file_bytes=MANUAL_CONTENT.encode("utf-8"),
        original_filename=MANUAL_FILENAME,
        owner_user_id=str(owner_user_id),
        content_type="text/plain",
        visibility="public",
        product_id=product_id,
    )
    return summary.id


async def _reset_eval_shop(
    session: AsyncSession,
    *,
    media_service: MediaService,
    shop_id: str,
    owner_user_id: uuid.UUID,
) -> None:
    """删除本 Eval 店在 dev 库的数据（PG chunk / media / products / shop / category）。

    仅作用于本 Eval 店（按 owner 定位），是 ``--reset`` 的重置便利；
    种子写入仍一律经 service（本函数用 session 删除已存在的剧本数据）。
    """
    pg = create_async_engine(get_settings().ai_database_url)
    try:
        async with pg.begin() as conn:
            await conn.execute(
                text("DELETE FROM product_embedding_chunks WHERE shop_id = :s"),
                {"s": shop_id},
            )
    finally:
        await pg.dispose()

    products, _ = await ProductRepository(session).list_by_shop(
        uuid.UUID(shop_id), limit=100, offset=0
    )
    for product in products:
        for document in await media_service.list_documents_by_product(str(product.id)):
            await media_service.delete(document.asset_id)

    await session.execute(
        text(
            "DELETE FROM product_categories "
            "WHERE product_id IN (SELECT id FROM products WHERE shop_id = :s)"
        ),
        {"s": shop_id},
    )
    await session.execute(
        text("DELETE FROM products WHERE shop_id = :s"), {"s": shop_id}
    )
    await session.execute(text("DELETE FROM shops WHERE id = :s"), {"s": shop_id})
    await session.execute(
        text(
            "DELETE FROM categories WHERE name = :c AND NOT EXISTS "
            "(SELECT 1 FROM product_categories pc WHERE pc.category_id = categories.id)"
        ),
        {"c": CATEGORY_NAME},
    )
    await session.commit()
    print(f"--reset 已删除 Eval 店数据（owner={owner_user_id} shop={shop_id}）")


async def _reindex(shop_id: str) -> ReindexStats:
    """对 dev 库执行整店 reindex（组合根经 build_media_service）。"""
    async with get_session_factory()() as session:
        media_service = build_media_service(session)
        return await reindex_shop(
            shop_id=shop_id,
            db_session=session,
            media_service=media_service,
        )


async def _dump_chunks(shop_id: str) -> list[dict]:
    """读取 PG dev 中该店 chunk 明细（document_id/chunk_index/content_text 全文）。"""
    engine = create_async_engine(get_settings().ai_database_url)
    rows: list[dict] = []
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT document_id, source_kind, chunk_index, content_text "
                    "FROM product_embedding_chunks "
                    "WHERE shop_id = :shop_id ORDER BY document_id, chunk_index"
                ),
                {"shop_id": shop_id},
            )
            for row in result:
                rows.append(
                    {
                        "document_id": str(row.document_id),
                        "source_kind": row.source_kind,
                        "chunk_index": int(row.chunk_index),
                        "content_text": row.content_text,
                    }
                )
    finally:
        await engine.dispose()
    return rows


async def main() -> None:
    """种子入口：建店主/类目/店铺/商品/说明书 → reindex → 打印 ID 与 chunk 清单。"""
    parser = argparse.ArgumentParser(description="Eval 店种子（ai-ragas-eval）")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="删除既有 Eval 店数据后重建（升 snapshot / 改剧本时用）",
    )
    args = parser.parse_args()

    async with get_session_factory()() as session:
        media_service = build_media_service(session)
        owner_id = await _ensure_owner_user(session)

        existing_shop = await ShopRepository(session).get_by_owner_user_id(owner_id)
        if existing_shop is not None:
            if not args.reset:
                raise SystemExit(
                    f"Eval 店已存在（shop_id={existing_shop.id}）。"
                    "改剧本/升 snapshot 时请加 --reset 重建。"
                )
            await _reset_eval_shop(
                session,
                media_service=media_service,
                shop_id=str(existing_shop.id),
                owner_user_id=owner_id,
            )

        category_id = await _ensure_category(session)
        shop_id, products = await _create_shop_and_products(
            session, owner_user_id=owner_id, category_id=category_id
        )
        manual_asset_id = await _ensure_manual(
            session,
            media_service=media_service,
            owner_user_id=owner_id,
            product_id=products[MANUAL_PRODUCT_NAME],
        )
        # media 上传仅 flush（MediaRepository.insert 不 commit），reindex 用独立
        # session，须先提交 media 行与说明书写入，否则 reindex 读不到 media_document。
        await session.commit()

    stats = await _reindex(shop_id)
    chunks = await _dump_chunks(shop_id)

    print(
        json.dumps(
            {
                "seed_id": SEED_ID,
                "snapshot_candidate": "eval-drinkware-v2",
                "shop_id": shop_id,
                "owner_user_id": str(owner_id),
                "category_id": category_id,
                "products": products,
                "manual_asset_id": manual_asset_id,
                "manual_product": MANUAL_PRODUCT_NAME,
                "reindex": {
                    "documents_processed": stats.documents_processed,
                    "chunks_inserted": stats.chunks_inserted,
                    "documents_skipped": stats.documents_skipped,
                    "errors": stats.errors,
                },
                "chunks": chunks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
