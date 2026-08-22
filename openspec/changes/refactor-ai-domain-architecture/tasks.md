## 1. 规范成文

- [x] 1.1 新增 `docs/decision/ADR-013-AI域组合根与消费边界.md`：组合根=`deps.py`、业务域不准 import ai、查询过滤 vs 防腐层、NLU 只办事 / 转人工前端发起（实现留给 `ai-support-agent`）、不建空 router
- [x] 1.2 修订 ADR-012：读路径用词改为按会话范围过滤；Change 3 行不再把 `handler_mode` 注入写成唯一路径
- [x] 1.3 修订 `docs/architecture.md` §3/§4/§7：意图识别留后端 agent；前端功能级路由；AI 组合根说明
- [x] 1.4 更新 `.cursor/rules/app-layer-discipline.mdc` 与 `cross-domain-imports.mdc`：AI 不对称白名单 + service 禁止自装配

## 2. TDD — 失败测试（红）

> 只写测、不写实现。§2 完成前不得开始 §4–§6。2.1 测例已写（现红，待 §3 绿）。

- [x] 2.1 扩展 `tests/catalog/test_product_rag_source.py`：`ProductRagSource` 无 `price`；`get_product_for_rag_indexing` 上架返回源、下架/不存在返回 `None`
- [x] 2.2 改 CLI / indexing 测试：`media_service` 必传；断言 `reindex_product` 不调用 `list_products_for_rag_indexing(shop_id=None)`；断言不存在 `app.ai.service` 门面导出；**不编写** deps / 删门面实现
- [x] 2.3 编写检索测例：同店两商品 chunk 时 `retrieve_chunks(..., product_id=A)` 不含 B；省略 `product_id` 仍可返回多商品；**不编写** retrieve 实现
- [x] 2.4 编写 AST 合成用例：业务域 import `app.ai.*` 应违规；`app/ai/**` 除 `deps.py` 外 import 别域 `deps` 应违规、`deps.py` 取 `get_media_service` 应放行；**不编写** `DOMAINS` / R5 实现
- [x] 2.5 `devbox run -- task db:up` 后跑 §2.2–2.4，确认失败（红）

## 3. catalog 单商品语料接口（绿）

- [ ] 3.1 `ProductRagSource` 去掉 `price`；实现 `get_product_for_rag_indexing`（catalog service + 仓储按 id 且已上架；不存在/未上架返回 `None`）
- [ ] 3.2 跑绿 §2.1（`devbox run -- uv run pytest tests/catalog/test_product_rag_source.py -q`）

## 4. AI 组合根与砍门面（绿）

- [ ] 4.1 新增 `app/ai/deps.py` 的 `build_media_service`；删除 `_build_media_service`；`reindex_*` 的 `media_service` 必传；CLI `_run` 与测试 fixture 经 deps 装配
- [ ] 4.2 `reindex_product` / catalog_text 单文档改走 `get_product_for_rag_indexing`；删除 `app/ai/service.py`；调用方改 import `app.ai.rag.retrieval.service.retrieve_chunks`
- [ ] 4.3 `source_kind` 常量落入 `app/ai/rag/schemas.py`；chunking / indexing / CLI 改用常量
- [ ] 4.4 跑绿 §2.2

## 5. 检索按会话范围过滤（绿）

- [ ] 5.1 `vector_search` / `retrieve_chunks` 增加可选 `product_id`；SQL 按需 AND
- [ ] 5.2 跑绿 §2.3

## 6. AST 门禁（绿）

- [ ] 6.1 `DOMAINS` 加入 `ai`；业务域 import `app.ai.*` 一律违规（不走 service 白名单）
- [ ] 6.2 新增 R5：`app/ai/**` 除 `deps.py` 外禁止 import 别域 `deps`
- [ ] 6.3 跑绿 §2.4；`uv run python scripts/check_app_layer_discipline.py` 全绿

## 7. 本地验证与 CI

- [ ] 7.1 `devbox run -- task ci` 全绿
- [ ] 7.2 确认 GitHub Actions CI 全绿（`workflow_dispatch` 或 PR）

> **Apply 约定**：严格 TDD，§2 完成前不得开始 §4–§6。每个 apply 会话建议只完成 1 个 Task 节。
