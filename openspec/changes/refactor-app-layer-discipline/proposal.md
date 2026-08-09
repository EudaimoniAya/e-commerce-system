## Why

`refactor-app-layer-boundaries` 已消灭 deps 四反模式（① deps 建 schema ② deps 跨域 ③ 跨域两步 ④ 上帝 service），但**工程纪律尚未成文**——四反模式是规范缺失下 AI 的随机二选一累积而成。本 change 把上一轮推导定稿的 deps 边界规范（deps 两大类、跨域白名单、service 双形态、域内 current-object 模式）**落实为成文规范 + 全库代码改造 + AST lint 强制**，从根上消除 AI 偷懒绕过"跨域仅 service+schema"的机会。

上一轮的 Phase B/D 决策（`get_order_response(order_id, user_id)` service 内自解析鉴权、support `_get_current_shop_id` service 内自解析、cart checkout-batch 收进 service）是**暂缓形式**，与本次推导的规范（鉴权收进 deps `get_current_*`、业务不进 deps）冲突，予以推翻。

## What Changes

- **规范成文**（文档）：新增层纪律规范（rule + ADR + architecture 三载体），定义：
  - deps 两大类：**装配类**（`get_*_repository` / `get_*_service`，供注入）+ **解析类**（`get_current_*`，鉴权 + 实体解析，只被本域 router 消费）
  - **业务不进 deps**：deps 只做装配 + 纯横切鉴权，schema 权威出口只在 service
  - **跨域白名单两维**：跨域只碰对方 service 接口 + schemas（含 deps 里 service-provider）；禁 models / repository / current-object deps / 私有 `_*`
  - **service 双形态**：返 schema（跨域/响应）+ 返 ORM（本域 current-object deps 消费）；`get_*` 公开 / `_to_*` 私有
  - **域内 current-object 模式**：router `Depends(get_current_*)` 拿实体 → 传 service；`get_current_user_id` 作业务参数（engagement 等）合法
  - **上帝 service = 域内膨胀后果**：按实体拆 service、deps 分窄
- **全库改造**（行为不变）：
  - catalog：`update_product` 走 **A 方案**——新增 `get_current_product` deps（解析 product + 归属校验），service 收已鉴权实体
  - ordering：4 个订单端点鉴权收进 deps（`get_current_order_for_buyer` / 新增店主视角 deps）；`get_order_response` 改收 Order 实体
  - ordering/cart：4 处 cart 鉴权收进 deps（`get_current_cart_item` 等）
  - support：7 处店主解析升级为 `get_current_support_shop` deps（本域 deps 吃 catalog service，跨域 service 调合法）
  - deps 命名统一：`get_order_by_id` / `get_order_for_buyer` / `get_order_for_buyer_or_shop` → `get_current_*`
- **AST lint 强制**（最后一 Phase）：新增 `scripts/check_app_layer_discipline.py` 挂进 `task ci`，强制 `_*` 私有名不跨模块、跨域白名单、deps 两大类、薄 router、上帝 service 拆分
- **不引入 TID251 / import-linter**：TID251 是"目标导向"全局禁（无调用方概念，误伤域内），无法表达跨域白名单；全部用自写 AST 脚本

## Capabilities

### New Capabilities

- `refactor-regression`: 行为不变验证——全库改造后既有 HTTP API 路径、请求/响应 JSON schema 及业务语义保持不变，pytest 全绿

### Modified Capabilities

（无——本 change 行为不变，不修改既有 spec 的 REQUIREMENTS）

## Impact

- **业务域**：catalog、ordering（含 cart）、support、user、engagement（仅确认无改动）
- **代码**：各域 `deps.py` / `router.py` / `service.py` / `*_service.py`；新增 `get_current_*` deps 族
- **文档**：`.cursor/rules/`、`docs/architecture.md`、`docs/decision/ADR-010`（或并入 ADR-001）
- **CI**：Taskfile 新增 AST lint 门禁；新增 `scripts/check_app_layer_discipline.py`
- **依赖**：无新增第三方依赖
- **测试**：不新增 BDD 场景；以既有 406 量级 integration 全绿为准（行为不变）
