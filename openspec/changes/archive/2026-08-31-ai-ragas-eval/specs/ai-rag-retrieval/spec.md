## MODIFIED Requirements

### Requirement: Change 2 retrieval tests exclude RAGAS

检索（ACL / smoke / `product_id` 过滤）测试 SHALL 覆盖查询语义；**SHALL NOT** 要求 RAGAS、`context_recall`、faithfulness 或黄金测试集 Hit@K 作为检索测或默认 `task ci` 的必过门禁。`ragas` SHALL NOT 作为检索模块或默认 CI 的必装依赖。离线评测跑道（`ai-ragas-eval`）SHALL 使用可选依赖组，且 SHALL 以 `retrieve_chunks` 为检索入口。

#### Scenario: CI 检索测不依赖 ragas 包

- **WHEN** 默认 CI / `tests/ai` 下检索 integration 运行
- **THEN** SHALL NOT 将 `ragas` 列为本路径必需依赖

#### Scenario: 评测检索入口仍是 retrieve_chunks

- **WHEN** 离线评测 adapter 执行检索
- **THEN** SHALL 调用 `retrieve_chunks`
- **AND** SHALL NOT 改用 LangChain Retriever / Retrieval Chain 作为检索实现
