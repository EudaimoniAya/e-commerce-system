## Why

`app/` 生产代码在 router → service → repository 分层上已出现多种并存形态（router 跨域编排、`ShopService` 包办 shop/category/product、router 内 `_to_*` ORM 映射等）。代码量增长后这些问题才显性化；若不 refactor，后续 change 与 AI 生成会继续 drift。本 change **只改实现与分层**，**不**在本 change 定稿工程规范（规范留给后续 `docs-app-layer-discipline` change）。其中 Phase B 针对 deps 边界违规——**跨域只走 service+schema**，current-object deps 一旦跨域（support 用 catalog `get_current_shop`）即被当域公共面，诱发 deps 调 service 私有 `_to_*` 建 schema（`get_order_for_buyer_or_shop_response` / `get_current_user`），在 service 边界外绕出「deps 交互网」（破窗/架构侵蚀，问题累积导致分层边界被侵蚀）。

时机：`infra-ruff-style` 与 `test-testkit-rename` 已合入，mechanical 噪音已清场，适合做多 phase 结构 refactor。

## What Changes

- **Phase A（ordering）**：将 router 中跨域编排（如注入 `ShopService` 查店）与部分业务判断下沉至 `OrderService` / ordering `deps`；将 router 层 `_to_response` 等 ORM→Schema 映射迁入 service，router 保持薄适配（对齐 catalog / engagement 既有形态）。
- **Phase B（deps 规范化：ordering + user + catalog/support）**：跨域只走 service+schema，current-object deps 绝不跨域、绝不建 schema。① 消除建 schema deps——`get_order_for_buyer_or_shop_response`（ordering）与 `get_current_user`（user）在 deps 层 import 并调用 service 私有映射函数建 schema，改为 service 公开读方法（`OrderService.get_order_response` / `UserService.get_user_response`），`_to_*` 保持私有；② 消除跨域 deps——support 不再 `Depends(get_current_shop)`（catalog deps），改经 `ShopService.get_my_shop`。滑坡论证：一个跨域 deps 例外会诱发 deps 建 schema 交互网（破窗/架构侵蚀）。deps 规范全文留给 `docs-app-layer-discipline`。
- **Phase C（catalog）**：拆分「上帝」`ShopService` 为按实体划分的 service（至少 shop / product / category）及对应 `deps`；router 各端点注入语义匹配的 service；跨域公开能力以 narrow 方法或模块级 facade 暴露（具体拆分见 design.md）。
- **Phase 工作方式**：本 change 采用 **Phase > Task** 两级迭代（见 design.md）；Phase A 闭环 → Phase B（deps 规范化）→ Phase C（catalog 拆分）；每 Phase 完成 design 增量 + tasks 勾选 + CI 绿。
- **无 BREAKING**：HTTP API 路径、请求/响应 schema、业务语义保持不变；仅内部结构与 DI 变更。

## Non-goals

- **不** 在本 change 编写/定稿 ADR、`.cursor/rules` 工程纪律全文、cross-domain import CI 脚本（留给规范 change）。
- **不** 改 `support` router 的 `catalog.models.Shop` import（可后续 Phase（如 support Shop import）或规范 change 前单独做）。
- **不** 扩展 `app/` ANN、mypy、pre-commit。
- **不** 改 OpenSpec 主 spec 的 Purpose/TBD 或「工程纪律索引」（规范 change）。

## Capabilities

### New Capabilities

- `refactor-regression`：行为不变回归验收（非新业务；delta spec 仅约束 CI/对外 API 与 refactor 前一致）

### Modified Capabilities

（无——对外 Requirement 与 BDD 场景不变；回归现有 ordering / catalog 相关 spec 的 Scenario 即可验收。）

## Impact

| 域 | 影响 |
|----|------|
| **ordering** | `router.py`、`service.py`、`deps.py`；可能调整测试 import/mock |
| **user** | `deps.py`、`service.py`、`router.py`（仅 GET /users/me 读路径） |
| **catalog** | `deps.py`（`get_current_shop` 退回域内私有） |
| **support** | `router.py`（店主路径不再跨域 `get_current_shop`）、`service.py`（可选：新增本店解析 helper） |
| **infra** | 无 |
| **tests** | 现有 integration 测试应全绿；无新 BDD 场景 |

**分支**：`refactor/app-layer-boundaries`  
**短标签**：`[layer-boundaries]`  
**Commit scope**：Phase A → `ordering`；Phase B → `ordering` + `user` + `support`（deps 规范化）；Phase C → `catalog`
