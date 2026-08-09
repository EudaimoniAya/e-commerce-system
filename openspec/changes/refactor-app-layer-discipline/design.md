## Context

- **现状**：`refactor-app-layer-boundaries` 已消灭 deps 四反模式（① deps 建 schema ② deps 跨域 ③ 跨域两步 ④ 上帝 service → 上帝 deps），归档于 `openspec/changes/archive/2026-08-09-refactor-app-layer-boundaries/`，PR #34 已合入 `dev`。反模式完整记录见 `docs/troubleshooting/deps-跨域两步与上帝service反模式.md`。
- **遗留问题**：规范未成文。上一轮 Phase B/D 的部分决策是**暂缓形式**：`get_order_response(order_id, user_id)`（service 内自解析鉴权）、support `_get_current_shop_id`（service 内自解析）、cart checkout-batch 收进 service——它们把"鉴权/解析"塞进 service，与本次推导的规范（鉴权收进 deps `get_current_*`）冲突。
- **现状代码**（2026-08-09 盘点）：`get_current_shop`（catalog/deps.py）直吃 `get_shop_repository`（违规，应改经 service）；`update_product` 在 service 内 `get_shop_context` + owner 校验（类型2，应改 A 方案）；ordering 4 端点 + cart 4 端点鉴权散在 service；support 7 处店主解析用 `_get_current_shop_id` service 内自解析（跨域，但可升级为本域 current-object deps）。
- **约束**：HTTP API 与 BDD 行为不变；本 change 行为不变，不新增 BDD 场景；遵循 ADR-001 跨域 service + schema；不引入 TID251 / import-linter（理由见 Decision 5）。
- **分支**：`refactor/app-layer-discipline`；短标签 `[app-discipline]`。

## Task 组织

本 change 方案已定稿（规范骨架 + 改造清单 + AST 方案），无需探索式推进，故直接按业务域分组 Task（`openspec/changes/refactor-app-layer-discipline/tasks.md`），每域一个分组、逐步闭环：规范成文 → catalog → ordering → cart → support → user → AST lint。每个 Task 完成后 `devbox run -- task ci` 验证行为不变。

## Goals / Non-Goals

**Goals:**

- **规范成文**：deps 两大类（装配/解析）+ 业务不进 deps + 跨域白名单两维 + service 双形态 + 域内 current-object 模式 + 上帝 service 后果，落 rule / ADR / architecture 三载体。
- **全库改造**：catalog `get_current_product`（A 方案）、ordering 4 端点鉴权收进 deps、cart 4 处鉴权收进 deps、support 升级 `get_current_support_shop`、deps 命名统一 `get_current_*`。行为不变。
- **AST lint 强制**（Task 7）：`scripts/check_app_layer_discipline.py` 挂进 `task ci`。
- 全 change 结束：pytest 406 量级全绿，对外 API 无变化。

**Non-Goals:**

- 不引入 TID251 / import-linter（Decision 5）。
- 不新增 BDD 场景（行为不变）。
- 不涉及 media 域与 infra 域的 deps 改造（media 无 current-object deps；infra/auth 的 `get_current_user_id` 是无域耦合基底，全域共享合规）。
- 不改 AI 域（未实现）。
- 不拆 `ordering/router.py` 物理文件结构（只收编鉴权逻辑）。

## Decisions

### 1. deps 两大类：装配类 + 解析类

**选择**：deps 全部职能归并为两大类——

| 类 | 成员 | 职责 | 消费方 |
|----|------|------|--------|
| **装配类** | `get_*_repository`、`get_*_service` | 构建依赖对象树（组合根） | 本域 service 构造器 / 本域 router / 其他 service deps |
| **解析类** | `get_current_*`（含 infra `get_current_user_id`） | 鉴权 + 解析请求上下文实体/原语 | 仅本域 router |

**理由**：上一轮 deps 三分类（仓储 / service / current-object）是临时切法；C 完成后梳理清——仓储 deps 与 service deps 本质都是"装配"（返回依赖对象供注入），current-object deps 与鉴权 gate 本质都是"解析鉴权"。两大类是**本质分类**，三/四小类是表象。四大反模式里 ①②③ 是"业务进 deps"，④ 是"装配层膨胀"，两大类直接对应。

**替代**：维持三分类 → 拒绝，B/D 的暂缓决策正是三分类下"把鉴权塞进 service"的产物；两大类把"鉴权解析归 deps、业务归 service"划到根上。

### 2. 业务不进 deps（推翻 B/D 的核心）

**选择**：deps 只做装配 + 纯横切鉴权（解析当前上下文）。**schema 权威出口只在 service**；**业务逻辑、编排、写操作一律不进 deps**。

**推翻上一轮决策**：
- ❌ `OrderService.get_order_response(order_id, user_id)`（Phase B）：service 内自解析买家/店主鉴权 → 改为 `get_current_order_for_buyer_or_shop` deps 鉴权，service 收已鉴权 Order 做映射。
- ❌ `UserService.get_user_response(user_id)`（Phase B）：同上，user 域加 `get_current_user` deps。
- ❌ support `_get_current_shop_id` service 内自解析（Phase D）：改为本域 `get_current_support_shop` deps。
- ❌ cart `CartService.get_checkout_batch(batch_id, user_id)` service 内归属校验（Phase D）：改为 `get_current_checkout_batch` deps。

**保留**：
- ✅ `get_current_user_id`（infra/auth，返 uuid 原语）——无域耦合鉴权基底，全域共享合规。
- ✅ `get_order_for_buyer_or_shop` → 更名 `get_current_order_for_buyer_or_shop`，本身已是 deps 鉴权形态（保留）。

**理由（滑坡论证）**：一旦"鉴权解析"从 deps 移进 service，service 方法签名被迫带 `user_id` 并自解析——跨域调用方为复用会依赖这些签名，service 边界被侵蚀；回到"跨域两步 / deps 建 schema"的反模式老路。鉴权留在 deps，service 收"已鉴权实体"，边界才干净。

### 3. 域内 current-object 模式（router 拿实体 → 传 service）

**选择**：同域 router `Depends(get_current_*)` 拿实体 → 传给本域 service 方法。service 收**已鉴权实体**（返 schema 或返 ORM），不再自解析鉴权。

**与跨域的区别**：跨域上下文（如 support 解析 catalog shop）仍由 service 一步自解析（Phase D 保留）——因为 support 的 router **不能** `Depends(catalog 的 get_current_shop)`（那是反模式② 跨域 current-object deps）。support 升级的是**本域 deps** `get_current_support_shop`（内部吃 catalog service，跨域 service 调合法）。

**关键区分（决定改造范围）**：`get_current_user_id` 有两种用法——
- **业务参数**（engagement 全部、`create_shop` 等）：user_id 就是业务数据本身，service 直接读写本域表 → **不动**。
- **自解析实体**（`update_product` 等）：service 拿 user_id 解析实体 + 鉴权归属 → **改为 get_current_* 模式**。

按此区分，改造清单（上一轮盘点）：
- catalog：`update_product`（1 处）→ A 方案
- ordering：`pay_order`、`batch_pay`（同域 Order 鉴权）→ 收进 deps；`create_order_by_seller`、`get_order`、`create_shipment`、`list_shop_orders`（跨域解析 catalog shop）→ **保留 service 自解析**（跨域）
- ordering/cart：`update_cart_item`、`delete_item`、`checkout`、`checkout-batch`（同域 CartItem/batch 鉴权）→ 收进 deps
- support：7 处店主解析 → `get_current_support_shop`
- user：`get_user_response` / `update_profile` → user 域加 `get_current_user` deps（返 User ORM）

**理由**：domain 内"鉴权+ORM"解析是 FastAPI 惯用法（fixture 类比：deps 提供请求上下文）。`get_current_*` 命名即信号——路由看到就知"已鉴权"。

### 4. service 双形态：返 schema + 返 ORM

**选择**：service 同时有两种公开方法——
- **返 schema 的**：`get_my_shop` → `ShopResponse`（跨域/响应用）
- **返 ORM 的**：`get_shop_or_404` / `get_order_or_404` / `get_current_product` 依赖的解析方法 → `Shop`（本域 current-object deps 用）

**理由**：不违反"schema 唯一权威出口"——返 ORM 的方法消费者是**本域 deps**，不对外。若强制 service 只返 schema，current-object deps 就拿不到实体，只能绕道 repo（回到 `get_current_shop` 直吃 repo 的违规）。

**命名**：`get_*` 公开 / `_to_*` 私有；解析实体方法 `get_<entity>_or_404`（有 IO/鉴权）。

### 5. AST lint 强制，不用 TID251 / import-linter

**选择**：不引入 TID251（banned-api），不用 import-linter；自写 `scripts/check_app_layer_discipline.py`（Python AST）。

**理由**：
- **TID251 是"目标导向"全局禁**：实测 `"app.catalog.models"` 会拦 `app/catalog/deps.py` 自己的 `from app.catalog.models import Shop`（域内合法 import 误伤）。它没有"调用方"概念，无法表达"跨域禁、域内允许"的白名单语义——与规范方向相反。
- **TID251 无 glob**：实测 `app.*.models`、`app.catalog.deps.get_*` 等通配全部不生效，`_to_*` 私有名要手写全，写不全就漏。
- **import-linter 是模块级**：分不清 deps.py 里 `get_product_service`（合法）与 `get_current_shop`（非法）——无法成员级判断。
- **AST 能看到 import 发生在哪个文件**（`path.parts[1]` 即调用方域），天然支持"调用方导向"的白名单 + 成员级 + 结构规则（薄 router / 上帝 service / deps 两大类），一条规则覆盖 TID251 + import-linter 的全部能力及它们做不到的部分。
- **代价**：脚本自维护、边界要踩（多别名 import、多行 from、`__init__` 重导出）、启发式阈值要试调——但有 `scripts/check_no_test_cross_imports.sh` 先例，模式已验证。

### 6. catalog `update_product` 走 A 方案：`get_current_product` deps

**选择**：新增 `get_current_product(product_id, user_id)` deps，deps 内解析 product（404）+ 归属校验（product 属于当前 user 的 shop），返回 Product ORM；`ProductService.update_product(product, body)` 收已鉴权实体，只做业务更新 + media attach。

**替代 B 方案**：router 用 `get_current_shop` 拿 Shop，service 收 `(product_id, shop, body)` 查归属 → 拒绝，鉴权留在 service，不符合"鉴权进 deps"。

**理由**：A 把鉴权留在 deps，与 ordering 的 current-object 家族（`get_order_for_buyer_or_shop`）一致。

### 7. deps 命名统一 `get_current_*`

**选择**：所有"鉴权+ORM"解析 deps 更名：

| 现名 | 新名 |
|------|------|
| `get_order_by_id` | `get_current_order` |
| `get_order_for_buyer` | `get_current_order_for_buyer` |
| `get_order_for_buyer_or_shop` | `get_current_order_for_buyer_or_shop` |
| `get_current_shop`（catalog） | 保留（已合规，改经 service 吃 `get_shop_or_404`） |
| 新增 | `get_current_product` / `get_current_cart_item` / `get_current_checkout_batch` / `get_current_support_shop` / `get_current_user` |

**理由**：命名即信号——路由看到 `get_current_*` 就知"鉴权 + 实体已解析"。可被 AST lint 断言（`get_current_*` 只被本域 router import）。

### 8. 明确保留：多实体校验 + 跨域买家路径 + user 业务参数

**选择**：下列场景**不**收编进 deps（deps 单实体模式不适用或语义不属于"鉴权+实体解析"），保留 service 内处理：

| 场景 | 保留理由 |
|------|----------|
| `batch_pay`（ordering）逐笔 Order 买家校验 | 多 `order_ids`，`Depends` 针对路径参数单实体；逐笔归属校验是批量业务规则 |
| `checkout`（cart）逐笔 cart_item 归属校验 | 多 `cart_item_ids`，同上 |
| support 买家路径 `get_shop_context` + `_ensure_not_owner` | 跨域解析 catalog shop（本域 deps 不适用）；service 自解析是 Phase D 已确认的合法跨域形态 |
| `update_profile`（user）`get_by_id(user_id)` | user_id 是业务参数（更新当前用户自身资料，读自身实体），非"解析其他实体做鉴权" |

**理由**：`get_current_*` deps 的本质是"针对路径参数的鉴权 + 实体解析"。**多实体集合校验**（batch/checkout）是业务规则，硬塞 deps 会造出"接收 id 列表的 deps"——反模式③ 变体；**跨域买家路径**无法用本域 current-object deps（会变反模式②）；**更新自身资料**读的实体就是调用者自己，无"归属鉴权"可言。规范条文需明确"current-object deps 适用边界"，避免 AI 过度收编。

### 9. 规范成文载体：rule + ADR + architecture 三处

**选择**：规范三载体齐出——
- `.cursor/rules/app-layer-discipline.mdc`：AI 行为约束（MUST/MUST NOT），供后续编码遵守
- `docs/decision/ADR-010-应用层边界纪律.md`：架构决策留档（决策 + 理由 + 反模式对照）
- `docs/architecture.md` §4：域间协作规则增补（deps 两大类、跨域白名单、service 双形态）

**理由**：rule 管 AI 行为、ADR 管决策留档、architecture 管总览——三者强制力层级不同，都出是"企业级"做法。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| ordering 4 端点鉴权收进 deps 会动 `get_order_response` 签名（推翻 Phase B） | 按 Decision 2 逐项收编，每 Task 分组末全量 CI 406 全绿验证行为不变 |
| support 升级 `get_current_support_shop` 推翻 Phase D 的 service 自解析 | 确认跨域 service 调合法（本域 deps 吃对方 service，非反模式②），design Changelog 记录 |
| AST 脚本启发式规则（薄 router / 上帝 service）误报 | 阈值试调；先只强制确定规则（私有名/跨域白名单），结构规则降为警告 |
| 改造范围大（6 域 + 命名 + 文档 + lint） | 按 Task 分组推进（规范→catalog→ordering→cart→support→user→AST），每分组独立闭环 |
| AST 脚本自维护成本 | 复用 `check_no_test_cross_imports.sh` 模式；规范与脚本同 change 交付，强制同步 |

## Migration Plan

1. 从 `dev` 切 `refactor/app-layer-discipline`（已切）。
2. **Task 1 规范成文**：`.cursor/rules/app-layer-discipline.mdc` + ADR-010 + architecture §4 增补。
3. **Task 2 catalog**：`get_current_shop` 改经 service（补 `get_shop_or_404`）+ `get_current_product`（A 方案收 `update_product`）。
4. **Task 3 ordering**：deps 命名 `get_current_*` + 4 端点鉴权收进 deps + `get_order_response` 改收 Order 实体。
5. **Task 4 cart**：`get_current_cart_item` / `get_current_checkout_batch` 收编 4 处鉴权。
6. **Task 5 support**：`get_current_support_shop` 升级 7 处店主路径。
7. **Task 6 user**：`get_current_user` deps 收编读路径。
8. **Task 7 AST lint**：`scripts/check_app_layer_discipline.py` + Taskfile 挂 `task ci`。
9. PR → merge `dev` → archive change（sync `refactor-regression` delta 到主 spec）。

**Rollback**：按 Task 分组 revert commit；无 DB migration。

## Changelog

| 日期 | Phase | 摘要 |
|------|-------|------|
| 2026-08-09 | — | propose：规范成文 + 全库 current-object 改造 + AST lint。推翻上一轮 Phase B/D 暂缓决策（鉴权收进 deps `get_current_*`）。lint 用自写 AST 脚本，不用 TID251/import-linter（TID251 目标导向无调用方概念、无 glob，误伤域内 import）。support 升级 `get_current_support_shop`、全量纳入本 change、AST 作最后一 Phase——用户三确认。 |

## Open Questions

- ~~TID251 是否有用~~ → 实测否定：目标导向全局禁、无 glob、无调用方概念。用 AST。
- ~~support 是否升级~~ → 用户确认升级（本域 deps 吃 catalog service 合法）。
- ~~改造范围~~ → 用户确认全量纳入本 change。
- ~~AST 脚本时机~~ → 用户确认改造后作为最后 Task 7。
