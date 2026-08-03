# ADR-009：Redis 业务扩展与 AI 数据分层策略

- **状态**：已采纳
- **日期**：2026-07-31
- **背景**：`infra-redis` 已交付 Redis 8 单实例、`get_redis()`、dev/test 逻辑库隔离与 readiness 双依赖检查；user 域 `SmsOtpService` 为当前唯一业务消费者。架构探索（2026-07-31）评估 Redis 从「验证码桶」扩展至更多业务/AI 场景的可行性与优先级，并与 MySQL、pgvector、Outbox 等 AI 数据路径对齐。

## 背景与现状

### 当前 Redis 使用范围

| 层级 | 组件 | 用途 |
|------|------|------|
| infra | `app/infra/redis.py` | 连接池、`get_redis()`、`reset_redis()` |
| infra | `app/infra/readiness/` | MySQL + Redis 聚合就绪探针 |
| user | `app/user/sms_service.py` | OTP、日发送限流、验证失败计数 |

Redis key 前缀（已实现）：

| Key 模式 | 用途 | TTL |
|----------|------|-----|
| `sms:otp:{phone}` | OTP 存储（GETDEL 消费） | 300s（可配） |
| `sms:daily:{phone}:{YYYYMMDD}` | 日发送计数 | 86400s |
| `sms:verify_fail:{phone}` | 验证失败计数 | 900s（可配） |

设计文档曾规划 `sms:cooldown:{phone}`（60s 发送冷却），**尚未实现**；当前仅依赖日上限。

### 明确不使用 Redis 的既有决策

- **ordering 订单超时释放**：MySQL `orders.expires_at` + 懒释放（pay / 详情 / 列表路径）；`ordering-buyer-orders` spec 规定 **SHALL NOT** 依赖 Redis、MQ 或周期扫描。
- **业务域禁止** 自行 `Redis.from_url`；仅通过 `app/infra/redis.py` 访问（见 ADR-002、`infra-redis` spec）。

### 探索动机

在 engagement、RAG、推荐等 AI 相关能力落地前，需明确：**哪些场景应消费 Redis、哪些应走 MySQL/pgvector、哪些应暂缓**，避免重复造轮子或与架构文档冲突。

## 决策

### 1. 暂不创建独立的「Redis 业务扩展」change

**当前阶段不交付** 以 Redis 为主线的垂直切片（如 `redis-business-expansion`）。基础设施已满足现有与近期需求；下一个对 AI 路径更有价值的底座能力是 **`engagement` 域（浏览 + 收藏，MySQL）**，而非 Redis 新 consumer。

### 2. 延后项（记录意图，待独立 change）

| 能力 | 决定 | 建议后续 change |
|------|------|-----------------|
| JWT token 黑名单（登出/吊销） | **延后** | `user-jwt-blacklist` 或同类 user/infra 切片 |
| catalog 读缓存（商品/类目） | **延后** | 流量或延迟成为瓶颈后再做 `catalog-read-cache` |
| 订单 TTL 经 Redis 触发释放 | **不做** | 维持 MySQL 懒释放，不修改 ordering spec |
| `sms:cooldown` 发送间隔 | **可选、低优先级** | 可并入 user 域小改进，非阻塞项 |

### 3. AI 相关数据分层（Redis 非主存储）

AI 赋能的**数据主干**按以下分层，Redis **不承担**行为持久化或向量检索：

```text
MySQL（唯一业务写源）
  ├─ engagement：browse_events、user_favorites（Phase 2，未实现）
  ├─ ordering：order_items（购买信号，已实现）
  └─ catalog：商品元数据（已实现）

PostgreSQL + pgvector（AI 读副本，后期）
  └─ 商品描述、FAQ embedding → RAG 语义检索
  └─ 经 Transactional Outbox + worker 从 MySQL 异步同步

Redis（ephemeral / 热路径 / 横切，按需叠加）
  ├─ SMS OTP（已实现）
  └─ 后期可选：AI 任务状态、对话 session、推荐结果短缓存、AI API 限流
```

**结论**：向量与 RAG 检索走 **pgvector**，不是 Redis；推荐训练/推理的行为数据走 **MySQL（engagement + ordering）**；Redis 对 AI 仅为**辅助**（性能、会话、异步任务状态），非「赋能来源」。

### 4. 优先级：engagement 先于 Redis 扩展

| 顺序 | 能力 | 存储 | 与 AI 关系 |
|------|------|------|------------|
| 1 | 浏览 + 收藏 | MySQL `engagement` 域 | 推荐系统主行为信号 |
| 2 | events/outbox → pgvector | MySQL outbox + PostgreSQL | RAG 语料同步 |
| 3 | ai 域（RAG、推荐、客服） | Tool → 各域 service | 命令式交互 + 预计算数据 |
| 4 | Redis 任务状态 / 会话 / 限流 | Redis | 随 AI 异步或对话切片按需引入 |

### 5. Redis 后期可选场景（随 AI 切片引入，非预建）

| 场景 | 模式 | 说明 |
|------|------|------|
| 耗时 AI Tool / 报告生成 | `task:{uuid}` 存 status/result，TTL | 异步命令 + 轮询/SSE；**非** Outbox |
| 多轮对话 checkpoint | Redis 或 MySQL，TTL 短 | LangGraph 等框架常见 |
| 推荐 API 结果 | `cache:rec:{user_id}` EX≈60s | 算力缓存，非训练数据源 |
| AI 接口限流 | `ratelimit:ai:{user_id}` | 控 token 成本 |

**不在 PR 阶段引入 Kafka**；事件投递优先 **MySQL Outbox 表 + worker**（见 ADR-001、架构 §7.1）。Kafka 仅在未来多 consumer、高吞吐、回放需求明确时再评估。

### 6. Key 命名空间约定（扩展时遵循）

| 前缀 | 归属 | 示例 |
|------|------|------|
| `sms:*` | user | 已实现 |
| `auth:*` | user/infra | 黑名单（延后） |
| `cache:catalog:*` | catalog | 读缓存（延后） |
| `cache:rec:*` | ai | 推荐结果缓存（后期） |
| `task:*` | ai/infra | 异步任务状态（后期） |
| `ratelimit:*` | infra | 全局限流（后期） |

业务域 **SHALL** 在域内 service 封装 Redis 访问（如 `SmsOtpService`），**SHALL NOT** 在 router 或 ai 域直连 key；ai Tool 仍只调各域 **service**（ADR-001）。

### 7. 与 Outbox / 同步事务的边界

本项目 MVP 写路径以 **单 MySQL 事务 + 同步跨域 service 调用** 为主（如 checkout 扣库存），**不等于** Outbox 模式。

Outbox **仅**用于「业务已成功、副作用可延迟、可重试」的下游（如同步 pgvector），特征为：

- 同事务写入业务表 + `outbox_events`
- HTTP 不等待 worker
- 最终一致

**不得**将下单、扣库存等强一致路径改为 Outbox。

## 理由

### 基础设施已就绪，业务 consumer 不足

`infra-redis` 已完成连接、测试、CI、readiness；再建「空扩展」change 无演示价值，且易违反 YAGNI。

### AI 路径的瓶颈是行为数据与向量副本，不是 Redis

推荐依赖 `order_items` + engagement 行为；RAG 依赖 pgvector。无 engagement 表时，Redis 扩展无法推进 AI 演示。

### 延后项与现有 spec 一致

订单 Redis TTL 与 `ordering-buyer-orders` 冲突；读缓存与 JWT 黑名单对当前 MVP 非阻塞，独立切片更清晰。

### 控制运维与认知复杂度

项目已维护 MySQL + Redis + devbox；AI 阶段再加 PostgreSQL 与 Outbox worker。过早引入 Kafka 或大面积 Redis 业务 key 会增加 CI/本地环境负担，与 ADR-002 纪律不符。

## 后果

### 正面

- 明确 Redis 在 AI 架构中的**辅助定位**，避免误用 Redis 存向量或行为主数据。
- 后续 change 可按垂直切片独立交付（engagement → outbox/pgvector → ai），边界清晰。
- 探索结论可追溯，减少重复讨论。

### 负面 / 限制

- 登出后 JWT 在过期前仍有效，直至实现黑名单 change。
- catalog 公开读路径无缓存，高并发下压力在 MySQL（MVP 可接受）。
- AI 异步任务出现前，Redis 除 SMS 外仍「利用率偏低」；readiness 仍硬依赖 Redis。

## 演进路径

```text
当前
  Redis：SMS OTP
  行为：无浏览/收藏埋点

Phase 2（优先）
  engagement change → MySQL browse_events / user_favorites

AI 阶段
  events/outbox change → worker → pgvector
  ai change → Tool 调 service；按需 Redis task/session/ratelimit

按需独立 change
  user-jwt-blacklist
  catalog-read-cache
  user/sms：sms:cooldown（可选）
```

## 相关文档

- [ADR-002：测试与数据库/Redis 策略](./ADR-002-测试与数据库策略.md)（infra 提供形式、逻辑库隔离、`get_redis` 纪律）
- [ADR-001：单体多域架构](./ADR-001-单体多域架构.md)（域边界、Tool → service、Outbox 后期引入）
- [项目架构](../architecture.md) §3、§7（AI 路线图与数据架构）
- [infra-redis spec](../../openspec/specs/infra-redis/spec.md)
- [openspec archive：infra-redis design](../../openspec/changes/archive/2026-07-27-infra-redis/design.md)
- [openspec archive：user-phone-auth design](../../openspec/changes/archive/2026-07-28-user-phone-auth/design.md)（SMS Redis key 设计）
