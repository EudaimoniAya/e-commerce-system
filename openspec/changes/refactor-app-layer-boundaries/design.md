## Context

- **现状**：`app/ordering/router.py` 在部分端点注入 `catalog.ShopService` 做编排（`create_order_by_seller`、`create_shipment`、`list_shop_orders`），并在 router 内维护 `_to_response(order: Order)`；同域 `OrderService` 已注入 catalog 且部分列表方法已返回 `OrderResponse`，分层不一致。
- **现状**：`app/catalog/service.py` 单一 `ShopService` 承担 shop、category、product、库存与跨域读 facade（`get_purchasable_products`、`get_products_for_engagement` 等）；`get_shop_service()` 一次注入三个 repository + `MediaService`，router 全用 `Depends(get_shop_service)`。
- **对照**：`engagement/router.py` 为薄 router + 单 service + 直接返回 schema，为本 change 目标形态。
- **约束**：HTTP API 与 BDD 行为不变；本 change **不写**工程规范定稿（后续 `docs-app-layer-discipline`）；遵循 ADR-001 跨域 **service + schema**（实现层面收拢，不在本 change 新增 CI 脚本）。
- **分支**：`refactor/app-layer-boundaries`；短标签 `[layer-boundaries]`。

## Phase 与 Task 层级（本 change 工作方式）

以往：**一个 OpenSpec change ≈ 一个垂直切片 ≈ 一次闭环**。  
本 change：**一个分支 / 一个 change，内含多个 Phase**；边看边改、避免多分支。

| 层级 | 含义 | 闭环标准 |
|------|------|----------|
| **Phase** | 高于 Task 的主题迭代单元（如 Phase A ordering、Phase B deps 修复、Phase C catalog） | design 增量 + 本节 tasks 全 `[x]` + `devbox run -- task ci` 绿 + 可选 commit |
| **Task** | Phase 内可勾选的具体步骤（与历史 OpenSpec tasks 同级） | 实现 + 勾选 |

- Phase **不替代** Task；tasks.md 在 `## Phase A` / `## Phase B` / `## Phase C` 下用 `## 1.` / `## 2.` Task 组，小步 checkbox 写 **Phase A / Phase B / Phase C Task X.X**（与 OpenSpec `- [ ] X.Y` 解析兼容）。
- Phase 完成后在 design.md **Changelog** 追加决策；**不**在本 change sync 主 spec 纪律全文。
- 后续若发现新 Phase（如 support `Shop` import），在 tasks/design **追加 Phase**，不必新开分支。

## Goals / Non-Goals

**Goals:**

- Phase A：ordering router **不再**注入 `ShopService`；ORM→Schema 映射集中在 `OrderService`（及必要时 `CartService`）；router 以「单 service + 返回 schema」为主。
- Phase B：deps 规范化——current-object deps 本域独用、绝不建 schema。消除 ordering + user 的建 schema deps（`get_order_for_buyer_or_shop_response` / `get_current_user`）与 support 跨域 `get_current_shop` 违规（见 Decision 2）。
- Phase C：**反模式 ④（上帝 service → 上帝 deps）**——catalog 按实体拆分 service 与 deps；router 端点注入语义匹配的 service；跨域调用方（ordering / engagement / support）改为依赖 **narrow** catalog 入口（见 Decision 4）。
- 全 change 结束：现有 pytest **406** 量级全绿，对外 API 无变化。

**Non-Goals:**

- 不定稿 ADR / cursor rules / cross-domain lint 脚本（规范 change）。
- 不改 support router 的 `catalog.models.Shop`（可后续 Phase 或规范前单独做）。
- 不拆 `ordering/cart_router.py` 的 `_to_cart_item_response`（除非 Phase A 顺带极小改动且测试仍绿；非必须）。

## Decisions

### 1. Phase 顺序：ordering（A）→ deps 规范化（B）→ catalog（C）

**选择**：A → B → C。

**理由**：Phase A 已闭环（router 不编排、service 返 schema）；Phase B 先做 deps 规范化——消除 ordering/user 建 schema deps（`get_order_for_buyer_or_shop_response` / `get_current_user`）与 support 跨域 `get_current_shop`，把依赖面收敛后再动 catalog；Phase C 拆分 `ShopService` 后需更新 ordering/engagement/support 的 catalog 依赖类型，若先做 C 会与 B 交叉冲突。

**替代**：先做 catalog 拆分 → 拒绝，ordering 的 deps 坏味道与 catalog 拆分会在 `service.py` / `deps.py` 上交叉改动。

### 2. Phase B — deps 规范化：current-object deps 本域独用、绝不建 schema

**核心原理**：跨域只走 service 接口 + schema；deps 是本域私有装配——**current-object deps（返回实体/原语的授权解析器）绝不跨域、绝不建 schema**（schema 由 service 产出）；**service deps 是唯一允许的跨域接线**（各域 service 依赖在 deps 汇聚）。理由（滑坡论证）：current-object deps 一旦跨域（support 用 catalog `get_current_shop`），deps 被当域公共面，诱发 deps 调 service 私有 `_to_*` 建 schema（`get_current_user`、`get_order_for_buyer_or_shop_response`），在 service 边界之外绕出「deps 交互网」——小违规悄然累积成架构侵蚀（破窗效应）。

**选择**：
- **ordering**：`OrderService` 暴露公开方法 `get_order_response(order_id, user_id)`（fetch → 404 → 懒释放 → buyer/店主鉴权 → 私有 `_to_order_response`）；`get_order` 读路径改为 `get_current_user_id` + service 方法；删除 `get_order_for_buyer_or_shop_response` 与 deps 内 `_to_order_response` import。（`get_order_for_buyer_or_shop` 保留——`cancel_order` 写路径仍需它返 ORM，且其为合法 current-object deps：本域、不建 schema。）
- **user**：`UserService` 暴露公开方法 `get_user_response(user_id)`（fetch → 404 → 解析 avatar → 私有 `_to_user_response`）；删除 `get_current_user` deps 与 `_to_user_response` / `_resolve_avatar_url` import；`GET /users/me` 改用 `get_current_user_id` + service 方法。（user 无写路径消费 current-user ORM，故 deps 直接删；401 语义由 `get_current_user_id` 鉴权保留。）
- **catalog/support**：support 店主路径不再 `Depends(get_current_shop)`（catalog deps），改经已注入 `ShopService.get_my_shop(user_id)` 解析本店（404 语义一致）；`get_current_shop` 退回 catalog 域内私有。

**命名定稿**：service 公开读方法用 `get_*`（有 IO/鉴权），映射函数保持模块级私有 `_to_*`（不再用公开 `to_*`）。

**规范范围**：deps 三分类 /「current-object deps 不跨域、不建 schema」规范全文**不**在本 change 定稿（留给 `docs-app-layer-discipline`）；本 Phase 消除现有违规。

### 3. Phase A — ordering 收编排与 `_to_*`

**Router 规则（本 Phase 目标态）**：

- ordering / cart **router** 仅 `Depends` **本域** `OrderService` / `CartService`（及 infra/auth/deps 解析 ORM 的 ordering deps，如 `get_order_for_buyer`）。
- **禁止** router `Depends(get_shop_service)` 或 `ShopService` 类型注解。

**Service 规则**：

- 将 router 内 `_to_response(order: Order) -> OrderResponse` **迁入** `OrderService`（可复用/合并已有 `_to_order_response`），公开写方法统一返回 `OrderResponse` / `PaginatedOrders` / `BatchPayResponse`（内部仍可用 ORM）。
- 下列用例编排 **迁入** `OrderService`（签名以 `owner_user_id` / `user_id` 为入口，内部 `self._catalog.get_my_shop`）：
  - 卖家建单（现 `create_order_by_seller` router 逻辑）
  - 店主发货授权（现 `create_shipment` router 内 shop 校验）
  - 店主订单列表（现 `list_shop_orders` router 内 `get_my_shop`）
- `pay_order` 的 buyer 校验：迁入 `OrderService.pay_order(user_id, order)` 或等价 deps，router 不再写 403 分支（保持语义：非买家 403）。
- `cancel_order` 的 buyer/seller `cancel_reason` 选择：迁入 service（router 只传 `user_id`）。
- `ordering/deps.get_order_for_buyer_or_shop` 保留 catalog 调用 **合理**（deps 层授权）；与 router 编排不重复即可。

**Cart**：`cart_router` 的 `_to_cart_item_response` 本 Phase **可选**迁移至 `CartService`；优先保证 `router.py` 与 `service.py` 主路径一致。

**验收**：`rg 'ShopService|get_shop_service' app/ordering/router.py` 无命中；ordering 相关 tests 全绿。

### 4. Phase C — catalog 上帝 service 拆分（反模式 ④：上帝 service → 上帝 deps）

**选择**：拆为三个 application service 类（同包内，文件名可 `shop_service.py` / `product_service.py` / `category_service.py`，或暂保留单文件三类）：

| Service | 职责（自原 `ShopService` 迁出） |
|---------|----------------------------------|
| **CategoryService** | `create_category`, `list_categories` |
| **ProductService** | 商品 CRUD/列表、`reserve_stock` / `release_stock`、`get_purchasable_products`、`get_products_for_engagement`、`validate_product_refs_for_shop`、media 解析 helper |
| **ShopService** | 店铺 CRUD、`get_my_shop`、`get_public_shop`、`get_shop_for_support` |

**Deps**：

- `get_category_service()`、`get_product_service()`、`get_shop_service()` 各注入所需 repository + `MediaService`（product/shop 需要 media；category 不需要）。
- **不再**有一个 deps 函数注入三个 catalog repository 仅为了「一个上帝类」。

**Router**：

- `/categories*` → `CategoryService`
- `/products*` → `ProductService`（店主写操作仍通过 `get_current_shop` 解析 shop，见 Decision 5）
- `/shops*` → `ShopService`

**跨域调用方更新**（Phase C 必做）：

| 调用方 | 现依赖 | 改为 |
|--------|--------|------|
| `OrderService` / `CartService` | `ShopService` | `ProductService`（库存/可购）+ `ShopService`（若仍需 `get_my_shop`）或仅 `ProductService` + service 内 shop 解析 |
| `FavoriteService` / `BrowseService` | `ShopService` | `ProductService.get_products_for_engagement` |
| `SupportService` | `ShopService` | `ShopService.get_shop_for_support` + `ProductService.validate_product_refs_for_shop`（或 shop service 委托 product 校验） |

**替代**：单一 `CatalogService` facade 包装三类 → 可接受，但类名须 honest，且 router 仍按端点注入子 facade；**不**继续叫 `ShopService` 包三类。

### 5. `get_current_shop` 与 ORM（Phase C 范围）

**选择**：Phase C **catalog 域内** router 仍可使用 `get_current_shop` → `Shop` ORM 供 `ProductService.create_product(shop, ...)`；**不**在本 Phase 强制改为 schema（support 跨域 import 留待后续）。

**理由**：拆分 service 已足够大；ORM 仅在 catalog router/deps 内，不扩大 scope。

### 6. 测试策略

**选择**：**行为不变** — 不新增 BDD scenario；以现有 `tests/ordering/**`、`tests/catalog/**` integration 全绿为准。Refactor 中若某测试 mock 了 `ShopService` 路径，随 Phase C 更新 mock 目标。

**TDD**：无新业务能力；改完每 Task 跑相关测试，每 Phase 末 `devbox run -- task ci`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| Phase C 动跨域注入面大 | 按 Decision 4 表逐项改 deps；Phase 末全量 CI |
| `service.py` 拆文件 import 循环 | product 依赖 shop 校验时用 shop_id UUID + shop service 方法，避免 product → shop ORM 泄漏 |
| 与「规范 change」重复文档 | 本 design 只记实现决策；纪律 MUST 留给下一 change |
| Phase 定义新范式 | 本 design §Phase 与 Task 写入 proposal/tasks，archive 时可摘入 ADR-008 附录（可选，非本 change 必须） |

## Migration Plan

1. 从 `dev` 切 `refactor/app-layer-boundaries`。
2. **Phase A**：按 tasks.md §Phase A 实现 → CI 绿 → commit（建议 `refactor(ordering) [layer-boundaries]: Phase A ...`）。
3. **Phase B**：按 tasks.md §Phase B 实现（deps 规范化：ordering + user + support）→ CI 绿 → commit。
4. **Phase C**：按 tasks.md §Phase C 实现 → CI 绿 → commit。
5. PR → merge `dev` → archive change（**不** sync 纪律类主 spec；仅 `refactor-regression` delta 若采用）。

**Rollback**：按 Phase revert commit；无 DB migration。

## Changelog

| 日期 | Phase | 摘要 |
|------|-------|------|
| 2026-08-08 | — | propose：Phase A ordering + Phase B catalog 拆分 |
| 2026-08-09 | Phase A | ordering 闭环：router 薄化 + OrderService 返 schema。跨域编排（`get_my_shop` 解析、buyer 校验、`cancel_reason` 角色分支）全部迁入 `OrderService`；写方法统一返回 `OrderResponse` / `BatchPayResponse`；读路径 `get_order` 经 schema deps `get_order_for_buyer_or_shop_response` 返 DTO（router 不再注入 service+ORM）。router 无任何 catalog import（DoD 达成）；`tests/ordering` 79 + 全量 CI 406 全绿。**命名决策**：映射统一为模块级私有 `_to_order_response`（与各域 `_to_*` 一致），deps 同域导入该私有函数（仿 `app/user/deps.py`）；读路径映射跨模块问题（Option C：鉴权收进 service 读方法）留待后续 change |
| 2026-08-09 | — | 追加 Phase B（deps 规范化：current-object deps 本域独用、绝不建 schema）：跨域只走 service+schema；`get_order_for_buyer_or_shop_response` / `get_current_user` 建 schema 违规 → 改为 service 公开读方法（`OrderService.get_order_response(order_id, user_id)` / `UserService.get_user_response(user_id)`），`_to_*` 保持私有；support 跨域 `get_current_shop` 违规 → 改经 `ShopService.get_my_shop`。滑坡论证：跨域 deps 例外诱发 deps 建 schema 交互网（破窗/架构侵蚀）。原 catalog 拆分顺延为 Phase C；规范全文留 `docs-app-layer-discipline` |
| 2026-08-09 | Phase B | deps 规范化完成：反模式 ①（deps 建 schema）与 ②（deps 跨域）已清除。ordering `get_order_response(order_id, user_id)` / user `get_user_response(user_id)` 收读路径，`_to_*` 保持私有（`get_order_for_buyer_or_shop` 保留给 cancel_order）；support 店主路径经 `ShopService.get_my_shop` 解析本店，`get_current_shop` 退回 catalog 本域。反模式 ③（写路径收编 / 路由两步编排）与 ④（上帝 service → 上帝 deps）另立 Phase，④ 由 Phase C 执行。行为不变：406 全绿 |

## Open Questions

- Phase C 是否将 `app/catalog/service.py` 物理拆为多文件（apply 时按可读性决定，默认拆）。
- `CartService` 的 `_to_*` 是否纳入 Phase A 最后一并迁移（可选）。
