## Context

- Change 1（`infra-ai-pgvector`）与 Change 2（`ai-rag-acl-index`）已归档。写侧（DocumentIR → chunk/embed → PG）与读侧雏形（`retrieve_chunks` + shop 过滤）可用。
- Change 2 留下的形状问题：`app/ai/service.py` 投机门面；`indexing/service.py` 内 `_build_media_service`（全仓唯一「service 调别域 deps」）；`reindex_product` 用 `list_products_for_rag_indexing(shop_id=None)` 扫全平台；`source_kind` 字面量分叉；`ProductRagSource.price` 不进语料却占字段。
- `scripts/check_app_layer_discipline.py` 的 `DOMAINS` 不含 `ai`，且业务域 import `app.ai.service` 会因「service 白名单」放行。AI 组合根未宣布，AST 套空。
- 会话结论（`docs/temp/2026-08-21-ai-domain-architecture-session.md` + 后续 explore）：本切片修 Change 2；终态（NLU、转人工、客服 router）写入 ADR-013，实现留给 `ai-support-agent`。
- 约束：跨域只走 service + schema；不新建表；无对外 HTTP 变更。
- 分支建议：`refactor/ai-domain-architecture`；短标签 `[ai-domain-architecture]`。

## Goals / Non-Goals

**Goals:**

- 宣布 AI 组合根（`app/ai/deps.py` 装配类），删除 service 自装配与投机门面。
- catalog 提供按 id 的已上架语料查询；单商品 reindex 不再全平台 list。
- 检索按会话范围过滤：仅店 / 店+商品；查询与索引分述。
- AST 覆盖 `ai`：业务域不得 import `app.ai`；AI service 不得 import 别域 deps。
- ADR-013 锁终态契约（NLU 只办事、转人工前端发起、防腐层=异构同步）。

**Non-Goals:**

- NLU、客服闭环、AI router、Outbox/队列、`rag/` 搬家、拆除 support `handler_mode` 列。

## Decisions

### 1. 本切片定位 = Change 2 修缮，不是 Change 3

**选择**：代码只改组合根、catalog 单商品接口、常量、检索可选 `product_id`。客服/NLU/转人工只写 ADR。

**理由**：没有会话就无法按 BDD 测 NLU；把两刀绑在一起无法 TDD。Change 3 的输入仍是 Change 2 落库的向量，修缮不改那条数据前提。

**替代**：并入 `ai-support-agent` → 拒绝，范围膨胀。只写 ADR 不改代码 → 拒绝，自装配会继续当样板。

### 2. 组合根是 `deps.py` 函数，不是 router，也不是 `Depends`

**选择**：新增 `app/ai/deps.py`，例如 `build_media_service(session: AsyncSession) -> MediaService`，内部调用 `app.media.deps.get_media_service` + `get_storage_backend`。CLI `_run` 与测试 fixture **直接调用**。不建 `router.py`，不写 `get_current_*`。

```text
app/ai/deps.py          唯一允许 import media.deps 的 AI 模块
        │
        ├─ CLI _run / 测试 fixture     media = build_media_service(session)
        └─ 将来 AI router              Depends(build_media_service) 同一函数
```

`reindex_product` / `reindex_shop` / `reindex_document` 的 `media_service: MediaService` **必传**。下架/不存在商品的净删路径 **SHALL NOT** 在判断 `product is None` 之前构造 MediaService（CLI 仍会传入；service 内部不得使用）。

**理由**：`Depends` 只是「有请求时调这个函数」。无 AI HTTP 时组合根仍要有落点，否则接线会再钻进 service。空 router 与要砍的门面同类。

**替代**：`wiring.py` 给 CLI/测试共用 → 拒绝，service 容易 `or build_*` 回头。装配写在 CLI 里、不建 deps.py → 拒绝，AST 没有「合法组合根文件」。

**跨域**：AI → media 走 `MediaService` 类型 + `get_media_service`（仅 deps）；AI → catalog 走 `list_products_for_rag_indexing` / `get_product_for_rag_indexing` + `ProductRagSource`。禁止 ORM/repository。

### 3. 相对 ADR-010 的不对称：业务域不得碰 AI

**选择**：业务域之间仍可 `from other.deps import get_*_service`。**任何业务域模块 SHALL NOT import `app.ai.*`**（含 schemas/service/deps）。AI 的 deps 是 AI 自用的，单体与将来独立部署都成立。

**理由**：用户原意不是「AI 永远没有 deps」，而是「别人的 deps/router 不准拿 AI」。方向仍是叶子：AI → 业务，不是对称网格。

**替代**：AI 也进 ADR-010 白名单（业务可 `get_ai_*_service`）→ 拒绝，catalog 下架路径会再预埋调 AI。

### 4. AST：把 `ai` 纳入门禁，并禁止「service 白名单」放行业务→AI

**选择**：

1. `DOMAINS` 增加 `ai`。
2. **R2 特判**：源模块为 `app.ai.*` 且当前域不是 `ai` → 一律违规（不走 service/schemas 白名单）。
3. **R5（新）**：路径匹配 `app/ai/**` 且 **不是** `app/ai/deps.py` 时，禁止 `from app.<业务域>.deps import ...`。

**理由**：现状 `indexing/service.py` 的 lazy import 与「业务 import `app.ai.service`」都漏检。R5 比「禁止 AI 一切 deps」更准：`deps.py` 必须能取 `get_media_service`。

**替代**：只加 `ai` 进 DOMAINS、不特判 → 业务仍可 import `app.ai.service`。只靠约定 → 正是 Change 2 漏网原因。

### 5. 砍门面；删除 API 不对外预留

**选择**：删除 `app/ai/service.py`。`retrieve_chunks` 只留在 `app.ai.rag.retrieval.service`。`delete_product_chunks` / `delete_document_chunks` **不再**作为可被「未来业务/事件」调用的门面；清理只经 reindex / orphan（indexing repository 私有/模块内方法可留）。

**理由**：门面假设的调用方（catalog 下架调删除）在决策 3 下非法。预留即投机分层。

**替代**：门面留到 Change 3 → 拒绝，YAGNI 且方向错。

### 6. catalog：`get_product_for_rag_indexing`；DTO 去掉 price

**选择**：`get_product_for_rag_indexing(product_id, *, session) -> ProductRagSource | None`。语义与 list 相同：仅 `is_published=True`；不存在或未上架 → `None`（不抛 404）。仓储可 `get_by_id` 再判上架，或 `WHERE id=? AND is_published`。`reindex_product` / catalog_text 单文档路径走此接口。`list_products_for_rag_indexing(shop_id=None)` **保留**给整平台运维，**禁止**被单商品路径当作查找用。

`ProductRagSource` 字段：`product_id`、`shop_id`、`name`、`description`、`is_published`。去掉 `price`。

**理由**：O(n) 是接口粒度不够逼出来的。价格走 Tool 查 MySQL（D2）。

**替代**：给 list 加 `product_id=` 过滤 → 拒绝，单点查询不应伪装成 list。

### 7. `source_kind` 常量集中在 `app/ai/rag/schemas.py`

**选择**：`SOURCE_KIND_CATALOG_TEXT = "catalog_text"`、`SOURCE_KIND_MEDIA_DOCUMENT = "media_document"`；CLI argparse `choices` 用同一对常量。chunking / indexing 禁止字面量。

### 8. 检索：可选 `product_id`；查询不叫 ACL

**选择**：

```text
retrieve_chunks(shop_id, query, top_k=5, product_id: str | None = None)
```

- `product_id is None`：`WHERE shop_id`（店铺泛咨询）。
- 传入 `product_id`：`WHERE shop_id AND product_id`（商品对话，避免用 B 的语料答 A）。
- 商品不属于该店或无 chunk → `[]`。
- SQL 仍在 retrieval repository；不是独立组件。

用词：查询侧 = **按会话范围的过滤**。**防腐层** = MySQL↔pgvector 同步（CLI 现况；Outbox 以后）。索引写 `shop_id`/`product_id` 两列；读侧按会话选几个键。两路分述，不写进同一条 ingest 故事。

**理由**：向量只认像不像。ADR-007 只写了店隔离，商品对话不够。本切片只改 retrieve 契约，不实现 NLU 如何决定传不传 `product_id`（Change 3 用会话 product ref）。

**替代**：检索永远只隔店 → 拒绝，串货问答。本切片做客服传 ref → 拒绝，见决策 1。

### 9. 终态写进 ADR-013，本切片不实现

ADR-013 应写明、apply 时落盘：

- 前端消费的 AI 功能才有 router；RAG 是库，无 HTTP。
- 客服将来有自己的 router（不是「永远挂 support」）；本切片不建空路由。
- NLU **只负责任务**（检索 / Tool / …）。意图过载时 **文案建议** 转人工，**不**改会话模式。
- 会话默认 AI（不做店铺配置）。转人工 = 用户前端 → support。`handler_mode` 字段可留，发起方是用户不是 handler 注册表。
- 业务域永不 `Depends` AI。

修订 ADR-012：读路径「SQL 层 shop_id ACL」改为「按会话范围过滤」；Change 3 行去掉「必须 handler_mode=ai 注入」的唯一路径表述。

`architecture.md`：路由层「意图识别 / AI 分流」改为「前端功能级路由；消息级意图在后端 agent」。

### 10. 不建 `wiring.py`，不预建 `agents/` / `support_agent/rag`

**选择**：组合根只有 `deps.py`。目录维持 `app/ai/rag/{indexing,retrieval}` + `jobs/`。

## Risks / Trade-offs

- [业务测试仍断言 `ProductRagSource.price`] → 同步改 `tests/catalog/test_product_rag_source.py`；schema 单测若有。
- [调用 `app.ai.service` 的测试] → 改为 `app.ai.rag.retrieval.service`。
- [R2 特判过严，误伤将来 AI schemas 被业务读] → 决策 3 即禁止；事实类意图走 catalog Tool，不读 AI schema。
- [CLI 忘记传 media_service] → 类型/运行期立刻失败，优于静默自装配。
- [retrieve 加参后旧调用仍合法] → `product_id` 默认 `None`，既有店级测试保持。

## Migration Plan

1. 规范：ADR-013 + ADR-012 用词 + architecture + rule。
2. 失败测试（红，一门禁）：catalog / 组合根 / 检索 / AST 测例写齐后再实现。
3. catalog DTO/接口（绿）。
4. AI deps + 删自装配 + CLI/fixture 接线 + 删门面 + `source_kind` 常量（绿）。
5. retrieve 可选 `product_id`（绿）。
6. AST R2/R5（绿）。
7. `devbox run -- task ci`。

无库迁移。回滚：恢复门面与可选 `media_service`（不推荐）。

## Open Questions

无。范围与装配地点已在 explore 定稿。
