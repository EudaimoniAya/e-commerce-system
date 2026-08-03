## Context

MVP 已交付 user / catalog / ordering / engagement。ADR-007 暂缓 `merchant-tenant`，约定对话以 **`shop_id`** 隔离、演示阶段店主兼客服（`get_current_shop`）。本 change 新建 **support 限界上下文**，实现买家在店铺范围内咨询（可引用本店商品），为 `ai-support-agent` 预留 `handler_mode`、`author_role` 字段。

跨域纪律：support → `catalog.service` + schema；禁止 import catalog / ordering ORM 或 repository。

## Goals / Non-Goals

**Goals:**

- 可演示闭环：买家对 shop 首条 POST 创建会话并发消息 → 店主 inbox 可见并回复 → 双方拉历史
- `(shop_id, buyer_user_id)` 唯一会话；lazy create（inbox 无零消息会话）
- 消息标识：`sender_role` + `author_role`；会话 `handler_mode` 预留 AI 参与与前端展示
- product ref 校验经 catalog service；closed 店规则、禁自购、403/404 与 ordering 惯例对齐
- TDD + AsyncClient integration

**Non-Goals:**

- P2P、WebSocket、未读数、inbox 锁、handler 切换、AI 回复
- order ref 接受（MVP 422）；ref enrich
- ordering 域 service 变更（`validate_order_refs_for_conversation` 仅 design 预留）

## Decisions

### 1. support 域模块

```text
app/support/
  router.py           # /support/shops/* + /support/inbox/*
  service.py          # SupportService
  repository.py       # ConversationRepository, MessageRepository
  models.py             # SupportConversation, SupportMessage
  schemas.py            # Request/Response DTO
  deps.py               # 注入 SupportService；店主路径复用 get_current_shop
```

`main.py` 注册 `support.router`。

### 2. 数据模型（support 域）

#### `support_conversations`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `shop_id` | CHAR(36) | FK 语义 → `shops.id` |
| `buyer_user_id` | CHAR(36) | FK 语义 → `users.id` |
| `handler_mode` | VARCHAR | `ai` \| `human`；MVP 默认 `human`，创建时写入 |
| `last_message_preview` | VARCHAR(200) | 最近消息预览（截断 body；纯 ref 可为空或占位） |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | 任一方发消息时 bump |

约束：`UNIQUE(shop_id, buyer_user_id)`。索引：`ix_support_conversations_shop_updated`（`(shop_id, updated_at DESC)` 供 inbox）。

#### `support_messages`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | CHAR(36) PK | UUID |
| `conversation_id` | CHAR(36) | → `support_conversations.id` |
| `sender_role` | VARCHAR | `buyer` \| `shop` |
| `author_role` | VARCHAR | `human` \| `ai`；MVP 恒 `human` |
| `body` | TEXT NULL | 与 refs 至少一项非空 |
| `message_refs` | JSON NULL | `[{"ref_type":"product","ref_id":"..."}]`；MVP 仅 product |
| `created_at` | DATETIME | |

索引：`ix_support_messages_conversation_created`（`(conversation_id, created_at)`）。

migration：`011_support_conversations.py`，`down_revision = 010_engagement_browse`。

**替代方案（未采用）：** 独立 `support_message_refs` 表 — MVP 消息量小，JSON 列足够；order ref 后续可同结构扩展。

### 3. 消息语义（两维 + handler）

| 字段 | 层级 | 作用 |
|------|------|------|
| `handler_mode` | Conversation | 当前 AI 是否参与 + 前端展示（MVP 固定 `human`） |
| `sender_role` | Message | 对话哪一侧（buyer / shop） |
| `author_role` | Message | 实际撰写者（human / ai；MVP 恒 human） |

演进：`ai-support-agent` 写 `sender_role=shop, author_role=ai`；读 `handler_mode` 决定是否自动回复。

### 4. API（方案 A）

**买家侧**（`get_current_user_id`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/support/shops/{shop_id}/conversation` | 有 → 200 `ConversationResponse`；无 → **404** |
| POST | `/support/shops/{shop_id}/conversation/messages` | body `{body?, message_refs?}` → 201；lazy create |
| GET | `/support/shops/{shop_id}/conversation/messages` | 分页 ASC；无会话 → **404** |

**店主侧**（`get_current_shop`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/support/inbox` | 本店会话分页 DESC；含 `last_message_preview` |
| GET | `/support/inbox/{conversation_id}` | 详情；非本店 → **404** |
| GET | `/support/inbox/{conversation_id}/messages` | 分页 ASC |
| POST | `/support/inbox/{conversation_id}/messages` | `{body?, message_refs?}` → 201 |

分页 Query / envelope 符合 **infra-pagination**（`Paginated[T]`）。

### 5. 业务规则

#### 鉴权与状态码

| 场景 | 码 |
|------|-----|
| 未认证 | 401 |
| 买家 == 店主（禁自购延伸） | **403** |
| 非 buyer 且非该 shop 店主访问会话 | **404** |
| shop 不存在 | **404** |

#### closed 店铺

| 动作 | 结果 |
|------|------|
| 买家对 **closed** 店 **新发** 消息 | **422** |
| 已有会话 closed 后 **读** 历史 | 允许 |
| closed 后店主 **回复** | 允许（售后收尾） |

#### 消息体与 refs

| 规则 | |
|------|--|
| 空 body + 仅有 refs | 允许 |
| body 与 refs 全空 | **422** |
| body 长度 | ≤ 2000 |
| refs 数量 | ≤ 10；重复 `(ref_type, ref_id)` 去重后计数 |
| `ref_type=product` | catalog 校验归属 `shop_id`；未上架 **允许** |
| `ref_type=order` | MVP **422** |
| 响应 refs | 仅 `{ref_type, ref_id}`，不 enrich |

#### 会话生命周期

- 仅 `POST .../messages` 创建 conversation（lazy create，单事务）
- 发消息：bump `updated_at`、更新 `last_message_preview`（body 截断前 200 字符；无 body 时可空字符串或固定占位，实现统一即可）

### 6. catalog 跨域（本 change 新增）

`app/catalog/schemas.py` 新增：

```python
class ShopSupportContext(BaseModel):
    id: str
    status: str          # active | closed
    owner_user_id: str
```

`ShopService` 新增（无 HTTP）：

| 方法 | 说明 |
|------|------|
| `get_shop_for_support(shop_id: UUID) -> ShopSupportContext` | shop 不存在 → HTTPException **404** |
| `validate_product_refs_for_shop(shop_id: UUID, product_ids: list[UUID]) -> None` | 任一 id 不存在或不属于 shop → **422**；未上架允许 |

support 域注入 `ShopService`，禁止 import `catalog.models`。

**ordering 预留（本 change 不实现）：**

```python
validate_order_refs_for_conversation(shop_id, buyer_user_id, order_ids) -> None
```

### 7. SupportService 编排要点

**买家 POST message：**

1. `get_shop_for_support(shop_id)` → 404
2. 若 `buyer_user_id == owner_user_id` → **403**
3. 若 shop `closed` 且无已有 conversation → **422**；若已有 conversation 且 closed → 允许发（与 spec 一致：新发指首次 lazy create 路径 — **closed 店任何 POST 新发均 422**，已有会话的后续 POST 在 closed 下：spec 说 closed 后买家新发 422 — 需要 clarify）

Wait, user said:
- 买家对 closed 店新发 → 422
- 已有会话 closed 后读历史 → 允许
- closed 后店主回复 → 允许

For buyer POST on closed shop when conversation already exists - the user said "买家对 closed 店新发" which might mean new conversation only. But "新发消息" could mean any new message. Let me re-read...

"买家对 **closed** 店 **新发** 消息 | **422**"

This likely means buyer cannot send NEW messages to a closed shop at all. But then "closed 后店主回复 → 允许" - shop can reply.

What about buyer sending after shop is closed but conversation existed? The table said:
- 买家对 closed 店新发 → 422
- 已有会话 closed 后读历史 → 允许

So buyer cannot send new messages after close, only read. Shop can still reply. That's a bit asymmetric but makes sense for "shop closed, no new inquiries but finish existing threads".

I'll put in spec:
- Buyer POST when shop closed → 422 (whether or not conversation exists)
- Shop POST when shop closed → allowed if conversation exists

Actually re-read again. "买家对 closed 店新发" might mean starting a new conversation (lazy create) on closed shop. For existing conversation:
- Read allowed
- Shop reply allowed  
- Buyer new message?

The user table was:
| 买家对 **closed** 店 **新发** 消息 | **422** |
| 已有会话 **closed 后** **读** 历史 | **允许** |
| closed 后店主 **回复** | **允许** |

"新发" could mean "newly post/send" messages in general. I'll interpret as: buyer cannot POST messages when shop is closed (422). Shop can POST. Buyer can GET.

That's consistent and clear. I'll use that in spec.

4. 校验 body/refs 规则
5. `validate_product_refs_for_shop` if product refs
6. get_or_create conversation in same transaction (only if buyer POST and shop active - if closed, fail before create)
7. insert message, update preview + updated_at

**店主 POST：** verify conversation.shop_id == current shop; shop closed allowed.

### 8. 测试策略

| 层级 | 范围 |
|------|------|
| integration | `tests/support/test_support_buyer_*.py`、`test_support_inbox_*.py`；AsyncClient |
| unit | catalog service 新方法可选单测 |
| helper | `tests/support/helper/support.py` + `results.py` |

**Task 1 全部为红阶段**：只写测试与 helper，不写实现。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| closed 店买家不能续发但店主可回，前端需区分 | spec 明确；错误 422 |
| `last_message_preview` 与 ref-only 消息 | body 空时 preview 空字符串或 `[商品引用]` 占位，实现内统一 |
| 无 WebSocket，消息非实时 | Non-goals；轮询 |
| JSON refs 难 SQL 查询 | MVP 可接受；后续可拆表 |

## Migration Plan

1. `devbox run -- task db:up && devbox run -- task migrate`
2. 部署后 `/support/*` 可用；无 backfill
3. 回滚：`alembic downgrade -1` + 移除 router

## Open Questions

- （无阻塞项）`last_message_preview` 对纯 ref 消息的展示文案 — 实现时统一为空或短占位即可，不阻塞 propose。
