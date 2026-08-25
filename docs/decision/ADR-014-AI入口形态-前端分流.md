# ADR-014：AI 入口形态——前端分流

- **状态**：已采纳（决策已拍板；代码落地待 `refactor/ai-frontend-split` change）
- **日期**：2026-08-25
- **背景**：Change 3（`ai-support-agent`）以"后端转发"形态落地并合并（2026-08-25 归档）：AI 借 support 的 HTTP 端点当入口，`support/ports.py` 定义 `BuyerTurnAiHandler` Port，`main.py` 经 `register_buyer_turn_handler_factory` 注册工厂，`handler_mode` 会话状态机驱动分派。合并后复盘（详见 `docs/troubleshooting/ai域-入口形态-借support到前端分流.md`）：注册表是"借 support 入口"这一**权宜**的产物（权宜伪装成约束）；`handler_mode` 是**实现状态机**（需求期四要素全未知，必然摇摆，可消解）；前端分流可同时消解两者。

## 决策

### 1. AI 域开自己的 router，前端分流

- 新增 `app/ai/router.py`：买家鉴权 + 调 IntentController + 调 `support.service` 落库 + 返回结构化结果。
- 前端分别调用两个端点：AI 消息 → AI 端点；人工消息 → support 端点；列表读取仍走 support（`GET .../messages`，AI+人工混排）。
- 分流逻辑在前端（入口选择），后端**无模式状态**。`handler_mode` 驱动逻辑删除；PATCH 端点删除；字段留作历史数据，存量行不迁移。

### 2. 注册表与 Port 退役

- `register_buyer_turn_handler_factory`（support 侧）删除——support 不再消费 AI 能力。
- `BuyerTurnAiHandler` Port（`app/support/ports.py`）删除——无消费者。
- 意图注册表**机制**保留（`app/ai/agent/registry.py`），消费者从"support Port"变为"AI router 内部"。

### 3. 落库责任转移，controller 保持纯净

- 落库：AI router（接线层）调 `support.service` 写 `author_role=ai`——AI → 业务 service 是既定合法叶子方向（ADR-013 决策 2）。
- `controller/agent` 仍不 import support（纯逻辑，fake 可测）——change3"agent 不碰 support"纪律的形态前提变了，但核心逻辑层的纯净性不变。

### 4. 转人工信号：结构化响应，后端无状态

- AI 端点返回 `{type: ai_answer | fallback_human}`；τ 拒答 / 意图外 → `fallback_human`，前端据此切换端点。
- **`handler_mode` 驱动逻辑删除，后端不再持有会话级模式状态**；转人工信号经 AI 端点响应传递。**边界**：若将来出现真实需求（如卖家强制人工且前端不可绕的信任边界、合规要求后端持有模式状态），可作为独立决策重新引入（新 ADR 评审，不默认复活）；禁止借中间件读会话状态隐式回归——那是状态机还魂。

### 5. 保留不变

- RAG 是库（`retrieve_chunks` 唯一检索入口）；意图逐个 change 注册、禁空 handler；意图边界判据（有无结构化源）；意图间禁互调、底层功能共享经注册表/白名单；`author_role` 审计字段。

## 否决的观点

| 观点 | 否决理由 |
|------|---------|
| 继续借 support 入口（change3 形态） | 状态机熵（需求期摇摆）+ 注册表税（隐式依赖、测试重置、运行期失败） |
| 后端网关 / BFF 层分流 | 单体 + 单客户端，无多端共享需求；聚合放后端 service 即可（YAGNI） |
| 事件驱动异步（Outbox/Celery） | 客服是同步对话语义，不需要异步解耦 |
| 中间件做会话模式分流 | 读会话状态 = `handler_mode` 还魂（即使将来因信任边界引入显式模式状态，也应是显式字段 + 显式鉴权，不是中间件隐式分流） |
| 前端仍只调 support 一个端点、后端内部转发 | 同"继续借入口" |

## 后果

### 正面

- 注册表税消失（无全局可变状态、无测试重置、无运行期 KeyError）。
- 状态机消失，需求稳定（"收到 AI 消息就 AI 处理、人工消息就人工处理"）。
- AI 域获得独立 HTTP 契约（路由、鉴权、结构化响应），成为"服务提供者"而非"被动接线的叶子库"。

### 负面 / 限制

- AI → `support.service` 新依赖（AI 域从纯叶子变半叶子：AI → catalog + support）。
- 鉴权两份：AI 端点需自己的买家鉴权（可复用 support 鉴权依赖，AI→业务 import 合法）。
- 前端要懂两个端点 + 响应信号（复杂度从后端搬到前端，但搬到的是"不需要提前设计"的地方）。
- LLM 长延迟直面前端：SSE / 流式从可选项变体验刚需（独立 change）。

## 演进路径

```text
当前（change3 合并后）
  后端转发形态：借 support 入口 + Port/注册表 + handler_mode —— 本 ADR 宣布推翻

随后（refactor/ai-frontend-split）
  AI router 落地；support 删 AI 分支 / 注册表 / Port / PATCH；落库转 AI router
  测试：support 双模式测试删改、AI 端点测试新增、落库接线测试（SAVEPOINT 真库）
  规范：AI 域测试规范（L0-L3 按 IO 边界、fake 集中、替身术语）+ 架构规范成文

更后
  SSE 流式（AI 端点直出）；独立部署时 AI→support 落库改 HTTP/事件；
  事件防腐层（Outbox + Celery，商品改动自动增量索引）—— 与本 ADR 正交，不动摇入口决策
```

## 相关文档

- [ADR-013：AI 域组合根与消费边界](./ADR-013-AI域组合根与消费边界.md)（决策 4/5 被本 ADR 修订：AI router 提前落地）
- [change3 design.md](../../openspec/changes/archive/2026-08-25-ai-support-agent/design.md)（决策 1-3 被本 ADR 推翻，归档正文保留、末尾追加演进记录）
- [踩坑记录：AI 域入口形态复盘](../troubleshooting/ai域-入口形态-借support到前端分流.md)（决策来源：权宜伪装成约束、领域 vs 实现状态机、AI 推导自洽不保证前提正确）
- [change3 决策定稿](../temp/2026-08-24-ai-support-agent-change3-decisions.md)（被推翻形态的决策来源，前后对照）
