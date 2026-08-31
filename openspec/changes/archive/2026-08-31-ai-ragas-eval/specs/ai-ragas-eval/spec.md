## Purpose

离线 RAG 评测跑道：Eval 店语料快照、黄金测试集、叶子 adapter（`retrieve_chunks` + `rag_answer` 生成）、RAGAS Faithfulness 与 Context recall。不改变客服 HTTP / 编排器行为。

## ADDED Requirements

### Requirement: Golden eval dataset schema

系统 SHALL 在仓库提供黄金测试集（单轮 JSONL），每条样本 SHALL 含：稳定 `id`、`question`、`shop_id`、`product_id`（JSON `null` 表示整店检索）、以及 Context recall 所需的 `reference_context_ids`（`document_id:chunk_index` 形式）和/或 `reference` 参考答案。SHALL NOT 要求样本含会话消息或 HTTP 字段。条数 SHALL 在 20 至 40（含）之间。

#### Scenario: 样本可解析且含检索键

- **WHEN** 加载当前快照目录下的 `samples.jsonl`
- **THEN** 每一行 SHALL 能解析为含 `id`、`question`、`shop_id` 的对象
- **AND** `product_id` 缺省或为 `null` SHALL 表示调用 `retrieve_chunks` 时不传商品过滤（整店）
- **AND** 至少一条样本的 `product_id` SHALL 为非空商品 UUID 字符串

#### Scenario: 应召回 id 格式

- **WHEN** 样本含 `reference_context_ids`
- **THEN** 每一项 SHALL 匹配 `{document_id}:{chunk_index}` 且 `chunk_index` 为非负整数

### Requirement: Eval shop snapshot is versioned

系统 SHALL 将黄金测试集与语料快照绑定同一 `snapshot_id`（manifest）。Eval 店 SHALL 与 pytest 集成测试用的临时店铺数据分离。改切块策略或 embedder 后 SHALL 升 `snapshot_id` 或重对 `reference_context_ids`。Eval 店种子 SHALL 经 catalog **service**（及如需 media **service**）写入。

#### Scenario: manifest 声明快照

- **WHEN** 读取 `evals/golden/<snapshot_id>/manifest.yaml`（路径以实现为准，须在仓库内）
- **THEN** SHALL 含 `snapshot_id` 且与目录名一致
- **AND** SHALL 记录 Eval 店所用 `shop_id` 或可重建该店的种子标识

### Requirement: Leaf eval adapter fills RAGAS single-turn fields

评测 adapter SHALL 对每条黄金样本调用 `retrieve_chunks(shop_id, query=question, product_id=…)`（`product_id` 为 null 时省略或传 `None`）。`retrieved_contexts` SHALL 为各 `RetrievedChunk.content_text`。`retrieved_context_ids` SHALL 为 `{document_id}:{chunk_index}`。生成 SHALL 使用登记提示词 `rag_answer` 与 `LLMClient`，SHALL NOT 调用 `IntentController.handle_buyer_turn`，SHALL NOT 请求 `POST /ai/shops/{shop_id}/replies`。空检索时 SHALL NOT 调用生成 LLM，`response` SHALL 为 `suggest_human` 登记正文。

#### Scenario: 有 chunk 时填 Sample 检索字段

- **WHEN** spy/Fake 检索返回带 `document_id`、`chunk_index`、`content_text` 的 chunk 列表
- **THEN** adapter 产出的 `retrieved_contexts` SHALL 与 `content_text` 顺序一致
- **AND** `retrieved_context_ids` SHALL 为对应的 `document_id:chunk_index`

#### Scenario: 空检索不调生成

- **WHEN** `retrieve_chunks` 返回空列表
- **THEN** adapter SHALL NOT 调用 `LLMClient.generate`
- **AND** `response` SHALL 等于 `build_prompt_loader().load("suggest_human").text`

#### Scenario: 不走客服 HTTP 与编排器

- **WHEN** 执行评测 adapter（CI Fake 路径）
- **THEN** SHALL NOT 对 `/ai/shops/{shop_id}/replies` 发 HTTP
- **AND** SHALL NOT 实例化并调用 `IntentController.handle_buyer_turn`

### Requirement: Offline RAGAS scores Faithfulness and Context recall only

离线打分 SHALL 使用 RAGAS 的 Faithfulness 与 Context recall（LLM Context recall）。SHALL NOT 在本 change 启用 Context precision、Answer/Response Relevancy 或 Agent 轨迹指标。裁判 LLM SHALL 使用与生成分离的 GPT 兼容配置（独立 API 密钥 / base URL / model 环境变量）。`task ci` SHALL NOT 调用裁判、SHALL NOT 要求上述密钥存在。

#### Scenario: 离线指标集合

- **WHEN** 在已安装 eval 依赖且配置了裁判密钥的环境运行打分入口
- **THEN** 启用的 RAGAS 指标 SHALL 包含 Faithfulness 与 Context recall
- **AND** SHALL NOT 包含 Context precision 或 Answer Relevancy（或项目所用等价类名）

#### Scenario: CI 不跑裁判

- **WHEN** `task ci` 或默认 `pytest` 无 eval extra、无裁判密钥
- **THEN** 测试套件 SHALL 仍通过
- **AND** SHALL NOT 因缺少 `RAGAS_JUDGE_API_KEY`（或本 change 采用的裁判变量名）而失败

### Requirement: ragas is optional and not a production dependency

`ragas` SHALL 仅出现在可选依赖组（如 uv `eval` group），SHALL NOT 列入项目生产 `dependencies`。默认 `task ci` 环境 SHALL NOT 把 `ragas` 当作必装包。
