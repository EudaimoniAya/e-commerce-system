## 1. 规范成文

- [ ] 1.1 新增 `docs/decision/ADR-013-AI域组合根与消费边界.md`：组合根=`deps.py`、业务域不准 import ai、查询过滤 vs 防腐层、NLU 只办事 / 转人工前端发起（实现留给 `ai-support-agent`）、不建空 router
- [ ] 1.2 修订 ADR-012：读路径用词改为按会话范围过滤；Change 3 行不再把 `handler_mode` 注入写成唯一路径
- [ ] 1.3 修订 `docs/architecture.md` §3/§4/§7：意图识别留后端 agent；前端功能级路由；AI 组合根说明
- [ ] 1.4 更新 `.cursor/rules/app-layer-discipline.mdc` 与 `cross-domain-imports.mdc`：AI 不对称白名单 + service 禁止自装配

## 2. catalog 单商品语料接口（TDD）

- [ ] 2.1 红：扩展 `tests/catalog/test_product_rag_source.py`——`ProductRagSource` 无 `price`；`get_product_for_rag_indexing` 上架返回源、下架/不存在返回 `None`
- [ ] 2.2 绿：schema 去掉 `price`；实现 `get_product_for_rag_indexing`（catalog service + 仓储按 id 且已上架）
- [ ] 2.3 收尾：`devbox run -- uv run pytest tests/catalog/test_product_rag_source.py -q`

## 3. AI 组合根与砍门面（TDD）

- [ ] 3.1 红：CLI / indexing 测试改为必传 `media_service`；断言 `reindex_product` 不调用 `list_products_for_rag_indexing(shop_id=None)`；断言不存在 `app.ai.service` 门面导出
- [ ] 3.2 绿：新增 `app/ai/deps.py` 的 `build_media_service`；删除 `_build_media_service`；`media_service` 必传；CLI `_run` 与测试 fixture 经 deps 装配
- [ ] 3.3 绿：`reindex_product` / catalog_text 单文档改走 `get_product_for_rag_indexing`；删除 `app/ai/service.py`；测试改 import `app.ai.rag.retrieval.service.retrieve_chunks`
- [ ] 3.4 `source_kind` 常量落入 `app/ai/rag/schemas.py`；chunking / indexing / CLI 改用常量
- [ ] 3.5 收尾：`devbox run -- uv run pytest tests/ai tests/catalog/test_product_rag_source.py -q`

## 4. 检索按会话范围过滤（TDD）

- [ ] 4.1 红：同店两商品 chunk 时 `retrieve_chunks(..., product_id=A)` 不含 B；省略 `product_id` 仍可返回多商品
- [ ] 4.2 绿：`vector_search` / `retrieve_chunks` 增加可选 `product_id`；SQL 按需 AND
- [ ] 4.3 收尾：`devbox run -- uv run pytest tests/ai -q`

## 5. AST 门禁

- [ ] 5.1 `DOMAINS` 加入 `ai`；业务域 import `app.ai.*` 一律违规（不走 service 白名单）
- [ ] 5.2 新增 R5：`app/ai/**` 除 `deps.py` 外禁止 import 别域 `deps`；合成用例覆盖放行/拦截
- [ ] 5.3 收尾：`uv run python scripts/check_app_layer_discipline.py` 全绿

## 6. 本地验证与 CI

- [ ] 6.1 `devbox run -- task ci` 全绿
- [ ] 6.2 确认 GitHub Actions CI 全绿（`workflow_dispatch` 或 PR）
