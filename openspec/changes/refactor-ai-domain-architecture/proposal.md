## Why

Change 2（`ai-rag-acl-index`）把写侧索引与检索雏形交了出来，但组合根没宣布：门面零调用方、`indexing/service.py` 自装配 MediaService、单商品重建扫全平台、`source_kind` 字面量分叉。业务域有 AST 门禁，AI 不在 `DOMAINS` 里，审查套不到。Change 3（`ai-support-agent`）开张前必须先把形状和纪律钉死，否则客服会抄这套反模式。

本切片是 **Change 2 的修缮**（加一条读侧过滤契约），不是做客服。

## What Changes

- **砍投机门面**：删除 `app/ai/service.py`（`retrieve_chunks` 纯转发、`delete_*_chunks` 零调用方）。检索入口改为 `app.ai.rag.retrieval.service.retrieve_chunks`；chunk 清理由 indexing 重建/orphan 承担，不再预留「给业务域调用」的删除 API。
- **组合根落 `app/ai/deps.py`**：只放装配类（至少 `build_media_service(session)`）。CLI `_run` 与测试 fixture **普通函数调用**（现无 AI router，不用 `Depends`）。`indexing/service.py` 的 `media_service` **必传**；删除 `_build_media_service`；下架净删路径不得提前构造 MediaService。
- **跨域不对称（相对 ADR-010）**：业务域 `deps` / `router` / service **SHALL NOT** import `app.ai`。AI 的 `deps.py` 可取业务域 service-provider（如 `get_media_service`）；AI 的 service **SHALL NOT** import 别域 `deps`。
- **AST**：`check_app_layer_discipline.py` 覆盖 `ai` 域，强制上两条。
- **catalog 单商品语料接口**：新增 `get_product_for_rag_indexing(product_id)` → `ProductRagSource | None`（已上架才返回）。`reindex_product` **SHALL NOT** 再 `list_products_for_rag_indexing(shop_id=None)`。
- **`ProductRagSource` 去掉 `price`**（D2：价格不进语料，事实类意图走 Tool）。
- **`source_kind` 命名常量**收敛到 `app/ai/rag/schemas.py`（indexing / chunking / CLI 共用）。
- **读侧按会话范围过滤**：`retrieve_chunks` 增加可选 `product_id`。未传 = 仅 `shop_id`（店铺泛咨询）；传入 = `shop_id` + `product_id`（基于商品的对话）。查询侧不称 ACL；**防腐层**专指 MySQL↔pgvector 异构同步（本切片不实现 Outbox/队列）。
- **文档**：新增 ADR-013（AI 域组合根、消费边界、用词、Change 3 契约）；修订 ADR-012 读路径用词与 Change 3 描述；`architecture.md` 去掉「路由层做意图识别」的含糊画法。

**BREAKING（仅 AI 内部 / catalog RAG DTO，无 HTTP）：** `retrieve_chunks` 不再经 `app.ai.service`；`ProductRagSource.price` 删除；`reindex_*` 的 `media_service` 必传。

## Capabilities

### New Capabilities

- `ai-domain-composition`: AI 组合根（`deps.py` 装配类）、禁止 service 自装配、禁止业务域 import ai、AST 门禁；不引入 AI HTTP / 解析类 deps。

### Modified Capabilities

- `ai-rag-indexing`: 单商品重建走 catalog 按 id 查询；`source_kind` 常量；删除门面删除 API；MediaService 由组合根传入。
- `ai-rag-retrieval`: 入口改为 retrieval service（无门面）；可选 `product_id` 过滤；查询侧称「按会话范围过滤」。
- `catalog-products`: `ProductRagSource` 去 price；新增 `get_product_for_rag_indexing`。

## Non-goals

- **不做** NLU、客服问答闭环、τ 门禁、评测集（`ai-support-agent`）。
- **不做** 转人工动作（NLU 不改会话模式；转人工 = 前端 → support；本切片不改 support HTTP）。
- **不做** AI 客服 router、空 `router.py`、`rag/` 迁入 `support_agent/`。
- **不做** handler 挂在 support 上的权宜实现或拆除（support `handler_mode` 字段保留，本切片不接线）。
- **不做** Outbox / 消息队列防腐层（同步仍是 CLI reindex）。
- **不改** 业务 HTTP API 行为；不引入 LangChain Retriever。

## Impact

- **域**：`ai`（主）、`catalog`（RAG 只读契约）、`infra`（无运行时；AST 脚本）、文档（ADR-012/013、`architecture.md`、`.cursor/rules`）。
- **代码**：`app/ai/service.py`（删）、`app/ai/deps.py`（新）、`app/ai/rag/indexing/service.py`、`app/ai/jobs/reindex_cli.py`、`app/ai/rag/chunking.py`、`app/ai/rag/schemas.py`、`app/ai/rag/retrieval/{service,repository}.py`、`app/catalog/{schemas,product_service,repository}.py`、`scripts/check_app_layer_discipline.py`、对应 tests。
- **API**：无对外 HTTP 变更。
- **依赖**：无新第三方包。
- **测试**：indexing / retrieval / catalog RAG DTO + AST 合成用例；既有 pytest 全绿。
