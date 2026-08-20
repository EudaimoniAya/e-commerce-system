# ADR-012：RAG 读写分离——CQS 谱系定位、仓储判据与 change 宏观安排

- **状态**：提议中（Proposed，待拍板后 Accepted）
- **日期**：2026-08-20
- **背景**：`infra-ai-pgvector`（Change 1）与 `ai-rag-acl-index`（Change 2）归档后，AI 域写侧（多源语料 → DocumentIR → 向量落库）与读写双仓储（`app/ai/rag/indexing/`、`app/ai/rag/retrieval/`）并存。本 ADR 固化三件事：① 读写分离在 CQS→CQRS 谱系中的定位与边界；② 仓储拆分/合一的判据（为什么 RAG 拆两个仓储，而 CRUD 仓储与 LangChain VectorStore 合一都不矛盾）；③ RAG 功能在 change 1/2/3（及之后 change） 的宏观安排与依赖链。本 ADR 是 AI 域的宏观抓手文档：读它即可回答"读写为什么分、分到什么程度、各 change 承载什么"。

## 决策

### 1. RAG 是三条路径的流水线，不是单一系统

```text
写路径（离线）: MySQL 写源 → service DTO → DocumentIR（摄入层收敛）
                → chunking → embedder → pgvector 落库
读路径（在线）: query → vector_search（SQL 层 shop_id ACL）→ top-K → prompt
                → LLM → 答案（τ 门禁）
评测路径:      黄金集 → retriever/generator 分层指标 → 归因矩阵 → 失败样本回流
```

- 推论：三条路径的复杂度来源正交——写侧是**数据完整性**（幂等重建/级联清理/orphan），读侧是**查询语义**（相似度/ACL/top-k），评测是**质量测量**（recall/faithfulness/τ 标定）。正交 ⇒ 各自独立演进，互不污染。

### 2. 读写分离谱系定位：本项目停在"接口级 + DTO 雏形"，CQRS 完整形态是 YAGNI

```text
CQS（方法级）→ 接口/对象级 → 模型级（DTO → 投影表）→ 存储级（读副本/缓存）
                                     ↓ 达到模型级+存储级 = CQRS 完整形态
```

- 谱系定义：CQS = 方法级原则（Meyer：方法要么命令要么查询）；CQRS = 架构模式（Greg Young：读写不同模型/存储）。**"职责分离"从第一级就发生，不是 CQRS 专属特征**——CQRS 是分离穿透到模型级+存储级之后的命名，不是谱系的第四级。
- 本项目位置：`indexing/repository.py`（6 方法全命令）与 `retrieval/repository.py`（1 方法纯查询）＝**接口级分离**；`SearchHit(NamedTuple)` 返回形状 ≠ ORM 模型 ＝ **DTO 雏形**（模型级的第一只脚）。
- 前进判据（信号驱动，不提前）：读形状分叉（→ 显式读模型/DTO 层）；读 QPS/负载不对称（→ 读副本/存储分离）；数据量大（→ HNSW/IVFFlat，design D9 已标"Change 4+ 评估 ANN"）。
- 边界：完整 CQRS（投影表/事件溯源）在本项目**无触发信号**，禁止提前引入。

### 3. 仓储拆分判据：对称性（方法集 / 生命周期阶段 / 演进方向）

- 判据：**读写方法集对称、生命周期同阶段、演进方向耦合 → 合一；不对称、阶段不同、演进独立 → 分离**。
- 对照：
  - CRUD 仓储（catalog/user 等）：读写对称（每实体一套 get/save/delete）、同阶段（都服务请求生命周期）、演进耦合（改实体必然连坐读写）→ **合一 ✓**（拆分是碎片化）。
  - RAG 仓储：方法集 6:1 不对称（写侧生命周期方法 delete_by_*/bulk_insert vs 读侧单一 vector_search）、阶段不同（写侧=状态转换 ingest，读侧=稳态供给 serve）、演进独立（写侧→Outbox/Celery/增量索引，读侧→HNSW/rerank/缓存）→ **分离 ✓**。
- 推论：同一代码库两种形态并存**不是双重标准**，是同一判据在不同对称性下的正确输出。

### 4. 接口粒度判据：可替换性（LangChain VectorStore 合一不矛盾）

- 判据：**接口粒度由可替换性决定**——一个接口 = 一个后端实现；可插拔需求 → 粗接口，强隔离语义需求 → 细接口。
- 对照：LangChain `VectorStore`（add/delete + similarity_search 同接口）= 通用后端插槽（pgvector/Qdrant/Pinecone…）→ **合一 ✓**；本项目 = ACL 强制 + 幂等重建强隔离 → **分离 ✓**。
- 框架的分离发生在**工作流层**（Indexing API/RecordManager 写 vs Retriever 读），存储接口合一；本项目在工作流层和接口层都分离。
- 推论：两者都是同一判据系统的正确输出。自研分离的代价是显式分层，收益是结构保证（见 §5）。

### 5. 结构保证 vs 纪律保证：分离的收益边界

- 强度排序：**结构性不可能**（读侧对象物理上无写方法，违规无从发生）> **纪律代码化**（AST 门禁 `check_app_layer_discipline.py`，事后拦截）> 纯约定（靠人记）。
- 结构保证的范围（恒真命题）：代码行为层——两仓储间无任何 import/引用，写侧重构（改签名/换实现）在编译层面不可能触及读侧行为。
- 结构保证不覆盖：数据层——写侧数据 bug 通过同一张表传导给读侧，由 **τ 门禁 + 评测集 + 幂等重建（delete-then-insert）** 兜底。
- 推论：分离仓储管"代码行为不蔓延"，评测/重建管"数据可自愈"——两层各管一摊，合起来才是"写侧搞不坏读侧"的完整语义。

### 6. change 宏观安排：写读评测的落点与依赖链

| change | 内容 | 状态 | 承载 |
|---|---|---|---|
| change 1 `infra-ai-pgvector` | PG/pgvector 底座 + Embedder 抽象（协议/Mock/厂商骨架）+ readiness + CI | 已归档 | 写侧地基（**无多源语义**，纯基础设施） |
| change 2 `ai-rag-acl-index` | 多源语料（catalog_text + media_document）→ DocumentIR → chunk/embed → 落库；retrieval 仓储雏形；reindex CLI | 已归档 | **写侧完成** + 读侧存储接口 |
| change 3 `ai-support-agent` | 读侧闭环：检索消费 + agent 接入（handler_mode=ai）+ τ 门禁/无命中转人工 + 评测集/τ 标定 | 未开 | 读侧 + 评测路径 |

- 依赖链：change 3 的**输入 = change 2 落库的向量数据**；写侧理解（多源→DocumentIR→落库）覆盖 change 3 的"数据前提"；agent 编排/门禁/评测是 change 3 **独立的新设计**，不在写侧理解范围内。
- 推论：写侧完成 ⇒ change 3 的检索输入确定；change 3 聚焦检索质量/门禁/评测，不碰写侧代码。

### 7. 已知代价与失效条件

- 读仓储当前仅 1 方法（略超前）：价值 = 读侧演进的预留落点；若演进信号不来，合并回 service 成本低（判据失效时回退，不硬撑）。
- 术语边界：CQS = 方法级原则；CQRS = 架构模式；软版本 CQS 允许命令返回实体（SQLAlchemy 惯例），硬版本（Eiffel 字面）不强制。
- 失效条件：若未来读侧出现大量读写对称方法（方法集趋同），重新评估合并；若引入框架（LangChain 等），本决策的接口层分离让位于框架的接口粒度。

## 关联

- `ADR-011`（异构数据一致性：单一事实源/派生数据/逻辑外键）——写侧落库的一致性基础。
- `ADR-009`（Redis 业务扩展与 AI 数据分层）——change 优先级依据。
- `openspec/changes/archive/2026-08-17-infra-ai-pgvector`、`2026-08-20-ai-rag-acl-index`——change 1/2 的决策与 DoD。
- `app/ai/rag/indexing/repository.py`、`app/ai/rag/retrieval/repository.py`——本决策的代码载体。
- `docs/troubleshooting/集成测试-JWT-iat时钟回拨偶发401.md`——写读之外的运维层先例（环境时钟问题的实证方法论）。
