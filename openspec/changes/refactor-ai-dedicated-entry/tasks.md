## 1. TDD — 失败测试（红）

> 只写测、不写实现。§1 完成前不得开始 §2–§6。

- [x] 1.1 新增 AI replies integration：未认证 `POST /ai/shops/{shop_id}/replies` → 401；无会话 → 404 且不建会话。**不编写** router
- [x] 1.2 同上：买家先 POST support 非空 body，再 POST replies → 200，响应含 `text` / `conversation_id` / `assistant_message_id`；GET messages 含 `author_role=ai` 且 `sender_role=shop`。**不编写** 落库接线
- [x] 1.3 回看：先纯 product ref、再无 refs 问句、再 replies → 知识路径的 `product_id` 为卡片 id（可用 FakeLLMClient 固定 knowledge + spy retrieve 或等价注入）。助手行之后的新问句不得粘上墙外的旧 ref。**不编写** 回看逻辑
- [x] 1.4 纯卡片（仅 refs）后 replies → 200，`text` 为问候模板且 **不是** `suggest_human` 正文；落 `author_role=ai`。**不创建** `ask_about_product.yaml`
- [x] 1.5 生成抛错时 replies 仍 200 且助手正文为 `suggest_human`。**不编写** 失败兜底
- [x] 1.6 改 support 期望：`handler_mode=ai` 时买家 POST **不**新增 ai 行；删/改 `tests/support/test_ai_turn.py`（Port 注入场景退役）；inbox / buyer 列表里「默认 POST 带助手 preview」改为买家 preview。PATCH handler_mode 用例 **保留**。**不删除** Port 实现
- [x] 1.7 断言无 `BuyerTurnAiHandler` / `register_buyer_turn_handler_factory`；`build_intent_controller` 可调用；`build_buyer_turn_handler` 不存在；可加载 `ask_about_product`。**不编写** 改名与提示词文件
- [x] 1.8 `devbox run -- task db:up` 后跑 §1.1–1.7 相关 pytest，确认失败（红）

## 2. 建 AI 入口与读库组装（绿）

- [x] 2.1 登记 `app/ai/prompts/ask_about_product.yaml`；`app/ai/schemas.py` 响应契约；`build_buyer_turn_handler` 改名为 `build_intent_controller`（旧名删除）
- [x] 2.2 support.service：只读组装一轮（schema 消息列表或专用查询）+ `append_ai_message`；AI **不** import support ORM
- [x] 2.3 `app/ai/router.py` + `main.py` 挂载：鉴权、回看分支（问候 / `handle_buyer_turn` / 抛错→suggest_human）、200 响应
- [x] 2.4 跑绿 §1.1–1.5、§1.7 中提示词与 `build_intent_controller`（Port 符号测可仍红到 §3）

## 3. 拆 support Port（绿）

- [x] 3.1 删除 `ports.py`、工厂、`_run_ai_turn`、`main.py` 登记；买家 POST 不再写 ai 行
- [x] 3.2 跑绿 §1.6–1.7 余项；AST：support 无 `app.ai` import，AI → support.service 合法

## 4. tests/ai 目录归位

- [x] 4.1 新 replies 测放 `tests/ai/integration/`（或本刀约定的 IO 分层）；旧 `tests/ai/test_*.py` 能搬到 `unit/` / `component/` / `integration/` 则搬，**不拦** §3
- [x] 4.2 跑绿受影响的 `tests/ai` 与 `tests/support`

## 5. 活文档

- [ ] 5.1 修订 ADR-013：允许 `app/ai/router.py`；入口不再借 support；组合根仍是 `deps.py` 装配 + router 调用
- [ ] 5.2 修订 ADR-014：PATCH 与 `handler_mode` 窗口开关保留；删的是 POST 内分派。分支名 `refactor/ai-dedicated-entry`
- [ ] 5.3 修订 `docs/architecture.md` 客服路径（两步前端、无 Port）。**不改** `openspec/changes/archive/**`

## 6. 本地 CI

- [ ] 6.1 `devbox run -- task ci` 全绿

> **Apply 约定**：严格 TDD，§1 完成前不得开始 §2–§4。每个 apply 会话建议只完成 1 个 Task 节。短标签 `[dedicated-entry]`。
