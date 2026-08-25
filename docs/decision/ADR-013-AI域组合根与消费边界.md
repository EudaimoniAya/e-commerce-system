# ADR-013：AI 域组合根与消费边界

- **状态**：已采纳（`refactor-ai-domain-architecture` Task 1 成文；`ai-support-agent` apply 落地并修订决策 5）
- **日期**：2026-08-22
- **背景**：Change 2（`ai-rag-acl-index`）交付写侧索引与检索雏形后，组合根未宣布——门面零调用方、`indexing/service.py` 自装配 `MediaService`、AST 的 `DOMAINS` 不含 `ai`。本 ADR 定稿 AI 与业务域的不对称边界、组合根位置、查询过滤与防腐层用词，以及 Change 3（`ai-support-agent`）的终态契约（apply 落地首批仅知识类意图，Tool 类后续）。

## 决策

### 1. 组合根是 `app/ai/deps.py`，不是 router，也不要求当下用 `Depends`

- AI 组合根只放 **装配类**（如 `build_media_service(session)`）。CLI `_run` 与测试 fixture **普通函数调用**；将来有 AI router 时对同一函数使用 `Depends`。
- 无 AI HTTP 时 **SHALL NOT** 为占坑新建空 `router.py`，**SHALL NOT** 写 `get_current_*` 解析类。
- indexing service 的跨域依赖（`MediaService`）**必传**；service **SHALL NOT** import 别域 `deps` 或自行 `new`。

`Depends` 只是「有请求时调用装配函数」。无请求（CLI）时组合根仍然存在，只是调用方式不同。

### 2. 相对 ADR-010 的不对称：业务域不得碰 AI

- 业务域之间仍可 `from other.deps import get_*_service`（ADR-010 白名单）。
- **任何业务域模块 SHALL NOT import `app.ai.*`**（含 service、schemas、deps）。AI 的 deps 只给 AI 自己的入口用。
- 方向仍是叶子：AI → 业务 service + schema；不是对称网格。单体 in-process 与将来独立部署都成立——换的是调用介质，不是「catalog 来 Depends AI」。

### 3. 查询过滤 ≠ 防腐层

| 名称 | 含义 | 落点 |
|------|------|------|
| **按会话范围的过滤** | 这次检索能看见哪些 chunk | retrieval SQL：`shop_id`；商品对话再 AND `product_id` |
| **防腐层** | 业务库与向量库的异构同步 | 现况：`ai:reindex` CLI；以后：Outbox / 队列 + worker（独立 change） |

索引写入每行带上 `shop_id`、`product_id`；读侧按会话选几个键。两路分述，不写进同一条 ingest 故事。查询侧不称 ACL。

### 4. 消费形态：RAG 是库；前端消费的 AI 功能才有 router

- RAG indexing / retrieval **无 HTTP**，被客服 agent 进程内调用。
- 客服 **将来** 有自己的 router（经营助手写完后与之一同从「借用 support 入口」提出）。本切片不建空路由、不把 `rag/` 预迁到 `support_agent/`。
- 不投资「handler 挂在 support 上、后端偷偷切 AI/人工」作为终态。

### 5. Change 3 契约（已落地：首批仅知识类意图 + 转人工文案）

- **NLU 只负责意图分流**：产出 `{intent, confidence}`；进入知识 handler **当且仅当** `intent == knowledge` **且** `confidence ≥ TAU_THRESHOLD`（τ 最小版，单阈值）。意图过载 / 未识别 / 低置信 → **返回转人工文案（`suggest_human`）**，不调检索、**不**改会话模式。
- **意图注册表机制本刀落地，只注册 `knowledge`**（知识检索，消费 `retrieve_chunks`）。价格 / 库存 / 订单等 **Tool 类意图不注册、不占位**，随后续 change 逐个注册（8/18 分水岭：RAG 是一个意图）。
- 会话默认 AI（不做店铺级默认配置）。转人工 = 前端 **PATCH `handler_mode`** → support；`handler_mode=human` 时不进 NLU、不调 Port。
- 入口复用 support HTTP（买家 POST messages），**不建 AI router**（无 `/ai/*`）；AI 经 support `BuyerTurnAiHandler` Port 被同步调用（`main.py` 组合根注册 `build_buyer_turn_handler` 工厂）。

## 否决的观点

| 观点 | 否决理由 |
|------|---------|
| AI 也进 ADR-010「跨域可 Depends get_*_service」 | 业务下架路径会预埋调 AI，与单向叶子冲突 |
| 无 HTTP 就不建 `deps.py`，接线写在 CLI 里 | AST 没有合法组合根文件，接线会再钻进 service |
| 先建空 `router.py` / `wiring.py` 占坑 | 与 Change 2 投机门面同类 |
| NLU 执行转人工 | 改会话状态是 support 写操作；NLU 是只读任务路由 |
| 检索只隔店、不隔商品 | 商品对话会用 B 的语料答 A |

## 后果

### 正面

- Change 2 的自装配 / 门面有成文禁令，AST 可挂钩（`refactor-ai-domain-architecture` Task 5）。
- Change 3 开张时组合根与过滤契约已定，不必再借 support handler 当权宜。

### 负面 / 限制

- 与 ADR-010 业务域互取 service-provider 不对称，须靠 AST 特判（业务→`app.ai` 不走 service 白名单）。
- 会话模式与 NLU 的实现仍未落地，仅契约约束后续切片。

## 演进路径

```text
当前（refactor-ai-domain-architecture）
  规范：本 ADR + ADR-012 用词修订 + architecture + rules
  代码：deps 组合根、砍门面、catalog 单商品接口、retrieve 可选 product_id、AST

随后（ai-support-agent）——已落地
  NLU 意图分流（首批仅 knowledge）；默认 AI；前端 PATCH 转人工 → support
  retrieve 按会话 product ref 传 product_id

更后
  客服 / 经营助手抽出 AI router；Outbox 防腐层
```

## 相关文档

- [ADR-010：应用层边界纪律](./ADR-010-应用层边界纪律.md)（业务域组合根；本 ADR 给出 AI 不对称例外）
- [ADR-012：RAG 读写分离](./ADR-012-RAG读写分离与change宏观安排.md)
- [ADR-007：多租户扩展](./ADR-007-多租户扩展-设计与暂缓计划.md)（`shop_id` 隔离；商品过滤是读侧补充）
- [设计：refactor-ai-domain-architecture](../../openspec/changes/refactor-ai-domain-architecture/design.md)
- [项目架构](../architecture.md) §3.2 / §4 / §7
- `.cursor/rules/app-layer-discipline.mdc`、`cross-domain-imports.mdc`
