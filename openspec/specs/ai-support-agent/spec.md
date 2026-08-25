# ai-support-agent

## Purpose

店铺智能客服（ai 域）：NL 网关、场景隔离意图注册表、IntentController、知识类 handler（消费 `retrieve_chunks`）、提示词 Git 登记、LLM 协议（Mock / DeepSeek）、τ 最小门禁与转人工兜底。无 AI HTTP；经 support Port 被买家 POST 同步调用。

## Requirements

### Requirement: Intent registry registers only knowledge

系统 SHALL 为客服 agent 提供意图注册表与 IntentController。本 change 注册表 SHALL **仅**包含知识类意图（名称 `knowledge`），其 handler SHALL 调用 `app.ai.rag.retrieval.service.retrieve_chunks`。SHALL NOT 注册价格 / 库存 / 订单等无真实 handler 的意图。转人工兜底 SHALL 为注册表外的分支，SHALL NOT 作为注册意图占位。

#### Scenario: 注册表仅含 knowledge

- **WHEN** 查询本 change 客服 agent 的意图注册表
- **THEN** 已注册意图名称集合 SHALL 等于 `{knowledge}`

#### Scenario: 知识 handler 调用 retrieve_chunks

- **WHEN** 网关将一轮输入路由到 `knowledge`
- **THEN** handler SHALL 调用 `retrieve_chunks`（ai 域内），SHALL NOT 由 support 模块 import retrieval

### Requirement: NL gateway routes by intent and tau

系统 SHALL 提供 NL 网关：对买家本轮 `body` 产出 `{intent, confidence}`（`confidence` 为 `[0,1]`）。进入 `knowledge` handler SHALL 同时满足 `intent == knowledge` 与 `confidence >= TAU_THRESHOLD`。否则 SHALL 走转人工兜底分支，SHALL NOT 将未注册意图映射为 `knowledge`。

#### Scenario: 高置信 knowledge 进入检索

- **WHEN** 网关输出 `intent=knowledge` 且 `confidence` 大于等于配置 τ
- **THEN** SHALL 调用知识 handler

#### Scenario: 置信度低于 τ 走兜底

- **WHEN** 网关输出 `intent=knowledge` 但 `confidence` 小于 τ
- **THEN** SHALL NOT 调用 `retrieve_chunks`
- **AND** SHALL 返回转人工兜底文案

#### Scenario: 意图集外走兜底

- **WHEN** 网关输出的 intent 不是 `knowledge`（含 unknown / 价格库存等）
- **THEN** SHALL NOT 调用 `retrieve_chunks`
- **AND** SHALL 返回转人工兜底文案

### Requirement: Knowledge retrieve uses message product refs

知识 handler 调用 `retrieve_chunks` 时，`shop_id` SHALL 为当前会话店铺。`product_id` SHALL 按本条消息已校验的 product `message_refs`（去重后保留顺序）计算：0 个 → `None`；1 个 → 该 id；多个 → **最后一个**。SHALL NOT 使用正文符号解析商品。

#### Scenario: 无 ref 整店检索

- **WHEN** 本条消息无 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 为 `None`

#### Scenario: 单个 ref 按商品过滤

- **WHEN** 本条消息恰好一个 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 等于该 `ref_id`

#### Scenario: 多个 ref 取最后一个

- **WHEN** 本条消息有两个及以上 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 等于去重后列表的最后一项

### Requirement: Tau gate is a single threshold

系统 SHALL 从 Settings 加载 `TAU_THRESHOLD`（float，默认 0.3）。纯函数门禁：分数低于阈值则未通过。空 `retrieve_chunks` 结果 SHALL 视为未通过 τ：SHALL NOT 调用生成 LLM，SHALL 返回拒答 / 转人工文案。本 change SHALL NOT 实现多阈值标定或 RAGAS。

#### Scenario: 分数低于阈值未通过

- **WHEN** 调用门禁且 score 小于 `TAU_THRESHOLD`
- **THEN** 返回未通过

#### Scenario: 分数达到阈值通过

- **WHEN** 调用门禁且 score 大于等于 `TAU_THRESHOLD`
- **THEN** 返回通过

#### Scenario: 空检索不生成

- **WHEN** knowledge handler 的 `retrieve_chunks` 返回空列表
- **THEN** SHALL NOT 调用 LLM 生成答案
- **AND** 返回文案 SHALL 为拒答 / 转人工模板

### Requirement: Prompts are git-registered

系统 SHALL 在仓库内以 YAML 登记提示词，每份含 `id`、`version`、`template`。本 change SHALL 至少登记 `nlu_route`、`rag_answer`、`suggest_human`。加载器按 id 读取并填充变量；LLM 调用日志 SHALL 含 `prompt_id` 与 `version`。SHALL NOT 将提示词正文存数据库或外部 Hub。

#### Scenario: 按 id 加载 nlu_route

- **WHEN** 加载器请求 `nlu_route`
- **THEN** 返回的登记 `id` SHALL 为 `nlu_route`
- **AND** SHALL 含非空 `version` 与 `template`

#### Scenario: 缺少登记文件则失败

- **WHEN** 加载不存在的 prompt id
- **THEN** SHALL 抛出明确错误（测试可捕获），SHALL NOT 静默用空串

### Requirement: LLM client protocol with mock and DeepSeek

系统 SHALL 提供 `LLMClient` 协议（`generate(messages) -> str`）、`MockLLMClient`（可编程输出）与 `DeepSeekClient`（OpenAI 兼容 HTTP）。`LLM_PROVIDER=mock` 时 SHALL 使用 Mock；`deepseek` 时 SHALL 使用 DeepSeekClient。pytest / CI SHALL 使用 Mock，SHALL NOT 发起真实 DeepSeek HTTP。

#### Scenario: Mock 返回编程输出

- **WHEN** 注入 MockLLMClient 并设定固定字符串
- **THEN** `generate` SHALL 返回该字符串且不访问网络

#### Scenario: CI 不调用 DeepSeek

- **WHEN** CI 或默认 pytest 加载 LLM 配置
- **THEN** `LLM_PROVIDER` SHALL 为 `mock`

### Requirement: Handoff copy does not change handler_mode

转人工兜底 SHALL 只渲染已登记文案（`suggest_human`），SHALL NOT 修改会话 `handler_mode`，SHALL NOT 因兜底调用 `retrieve_chunks`。

#### Scenario: 兜底不写会话模式

- **WHEN** 网关走转人工兜底分支
- **THEN** 返回文案非空
- **AND** SHALL NOT 发出将 `handler_mode` 设为 `human` 的调用
