# ai-support-agent

## ADDED Requirements

### Requirement: Prompts include ask_about_product

系统 SHALL 在仓库内登记问候提示词（id `ask_about_product`，含 `id` / `version` / `template`）。纯卡片 replies 路径 SHALL 使用该模板。SHALL NOT 用 `suggest_human` 充当卡片问候。

#### Scenario: 可按 id 加载 ask_about_product

- **WHEN** 加载器请求 `ask_about_product`
- **THEN** 返回的登记 `id` SHALL 为 `ask_about_product`
- **AND** SHALL 含非空 `version` 与 `template`

## MODIFIED Requirements

### Requirement: Knowledge retrieve uses message product refs

知识 handler 调用 `retrieve_chunks` 时，`shop_id` SHALL 为当前会话店铺。`product_id` SHALL 按 **读库回看得到的** product refs（去重后保留顺序）计算：0 个 → `None`；1 个 → 该 id；多个 → **该次回看命中消息上的最后一项**。回看规则见 `ai-http-replies`（遇助手或店主人工消息停止）。SHALL NOT 使用正文符号解析商品。SHALL NOT 要求触发 `/replies` 的 HTTP 请求自带 refs。

#### Scenario: 无 ref 整店检索

- **WHEN** 回看无 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 为 `None`

#### Scenario: 单个 ref 按商品过滤

- **WHEN** 回看恰好一个 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 等于该 `ref_id`

#### Scenario: 多个 ref 取最后一个

- **WHEN** 回看命中的那条买家消息有两个及以上 product ref 且路由到 knowledge
- **THEN** `retrieve_chunks` 的 `product_id` SHALL 等于去重后列表的最后一项

### Requirement: Prompts are git-registered

系统 SHALL 在仓库内以 YAML 登记提示词，每份含 `id`、`version`、`template`。本 capability SHALL 至少登记 `nlu_route`、`rag_answer`、`suggest_human`、`ask_about_product`。加载器按 id 读取并填充变量；LLM 调用日志 SHALL 含 `prompt_id` 与 `version`。SHALL NOT 将提示词正文存数据库或外部 Hub。

#### Scenario: 按 id 加载 nlu_route

- **WHEN** 加载器请求 `nlu_route`
- **THEN** 返回的登记 `id` SHALL 为 `nlu_route`
- **AND** SHALL 含非空 `version` 与 `template`

#### Scenario: 缺少登记文件则失败

- **WHEN** 加载不存在的 prompt id
- **THEN** SHALL 抛出明确错误（测试可捕获），SHALL NOT 静默用空串
