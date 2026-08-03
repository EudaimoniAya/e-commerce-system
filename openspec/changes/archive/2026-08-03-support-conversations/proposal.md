## Why

ADR-007 规划 AI 演示路径为「买家在店铺页发起对话 → 后续 RAG/转人工」，对话能力以 **`shop_id`** 为管辖与隔离键，不依赖暂缓的 `merchant-tenant`。当前电商底座（user / catalog / ordering / engagement）已就绪，缺少 **support 域** 承载买家↔店铺客服会话，无法演示咨询闭环，也无法为后续 `ai-support-agent` 提供消息流主干。

## What Changes

- 新增 **support 域**（`app/support/`）：`support_conversations`、`support_messages` 表（新 migration `011`，依赖 head `010`）
- **买家 API**（Bearer JWT）：
  - `GET /support/shops/{shop_id}/conversation` — 有会话 200，无会话 **404**（前端「发起咨询」）
  - `POST /support/shops/{shop_id}/conversation/messages` — lazy create（首条消息同事务创建 conversation + message）
  - `GET /support/shops/{shop_id}/conversation/messages` — 消息分页（`created_at` ASC）
- **店主 API**（`catalog.deps.get_current_shop`）：
  - `GET /support/inbox` — 本店会话分页（`updated_at` DESC，含 `last_message_preview`）
  - `GET /support/inbox/{conversation_id}` — 会话详情
  - `GET /support/inbox/{conversation_id}/messages` — 消息分页（ASC）
  - `POST /support/inbox/{conversation_id}/messages` — 店主回复
- **消息模型**：`sender_role`（buyer \| shop）、`author_role`（human \| ai，MVP 恒 human）、`handler_mode`（ai \| human，MVP 默认 human）、`message_refs` JSON（MVP 仅 `product`）
- **catalog 跨域扩展**：`get_shop_for_support`、`validate_product_refs_for_shop`（service + schema，无 HTTP）
- 扩展 **pytest**：`tests/support/` helper + `tests/support/` 集成测；TDD 红→绿
- 更新 **docs/architecture.md**（support 域摘要）

## Non-goals

- P2P 私信、群聊、店主主动发起会话
- WebSocket / 推送 / 未读数 / inbox 锁
- `handler_mode` 切换 API、AI 自动回复（留给 `ai-support-agent`）
- `ref_type=order` 校验与接受（schema 预留，MVP 收到 order ref → **422**）
- ref enrich（ProductSummary 等）；响应仅 `{ref_type, ref_id}`
- 消息撤回 / 编辑、频率限制
- merchant 多租户、operator 协作

## Capabilities

### New Capabilities

- `support-conversations`：shop 管辖下的买家↔店铺客服会话（lazy create、inbox、消息历史、product ref）

### Modified Capabilities

- `catalog-products`：新增供 support 域调用的 service 方法（`get_shop_for_support`、`validate_product_refs_for_shop`）

## Impact

- **业务域**：新增 `support`；扩展 `catalog`（service 层 only）
- **API**：`/support/shops/{shop_id}/*`、`/support/inbox/*`（`main.py` 注册 support router）
- **数据库**：migration `011`；Alembic env 导入 support models
- **测试**：`tests/support/`、`tests/support/helper/support.py`；AsyncClient 集成测
- **文档**：`docs/architecture.md` §3 域表、§5 目录
- **演进**：对齐 ADR-007 → 后续 `ai-support-agent`；多租户时 inbox 鉴权改 `merchant.service`，表结构不变
