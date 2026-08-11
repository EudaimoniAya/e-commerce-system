## 1. 规范成文

- [x] 1.1 新增 `.cursor/rules/app-layer-discipline.mdc`：deps 两大类（装配/解析）、业务不进 deps、跨域白名单两维（service 接口 + schemas）、service 公开方法两类（schema 出口 + 业务方法，无返 ORM 透传 getter）、current-object 解析判据（纯读→本域仓储 / 业务读→service / 跨域→service，含状态无关/依赖切分）、域内 current-object 模式（`get_current_*` 只被本域 router 消费）、铁律条文（deps 无副作用 / service 自含业务完整性 / router 不直接序列化）、`_*` 私有名不跨模块
- [x] 1.2 ADR-010 已有 propose 骨架（`docs/decision/ADR-010-应用层边界纪律.md`，含决策 + 归谬推理 + 否决观点）；apply 时校验/完善
- [x] 1.3 增补 `docs/architecture.md` §4 域间协作规则：deps 两大类、跨域白名单、service 公开方法两类、current-object 解析判据、域内 current-object 模式
- [x] 1.4 更新 `docs/troubleshooting/deps-跨域两步与上帝service反模式.md` 的"规范对照"链接指向本 change 决策

## 2. catalog 域

- [x] 2.1 取消新增 `get_shop_or_404`（见 design Decision 4）；`get_current_shop` 保留直吃 `get_shop_repository`（本域纯读合规，无需改经 service）
- [x] 2.2 catalog/deps.py 新增 `get_current_product(product_id, user_id) -> Product`：**直吃本域仓储**（`get_product_repository` 解析 404 + `get_shop_repository` 归属校验）；`ProductService.update_product` 改收已鉴权实体（去 self 自解析鉴权），router 改用 `get_current_product`
- [x] 2.3 确认 `get_current_shop` 仓储直读保留（纯读合规）；验证 catalog 域内 import 全部合规（域内 models/repository 允许，跨域白名单不误伤）
- [x] 2.4 收尾：`devbox run -- task ci` 全绿，`tests/catalog` integration 全绿

## 3. ordering 域

- [x] 3.1 ordering/deps.py 命名统一：`get_order_by_id` → `get_current_order`、`get_order_for_buyer` → `get_current_order_for_buyer`、`get_order_for_buyer_or_shop` → `get_current_order_for_buyer_or_shop`；同步所有 router `Depends` 引用
- [x] 3.2 `get_current_order` 基础 deps 改**仓储纯定位**（`get_order_repository` 直读 + 404，删 `service.get_order_or_404` / `expire_if_needed` 调用；**仅基础 deps 无 service 依赖**——派生鉴权 deps 如 `get_current_order_for_buyer_or_shop` 仍吃 `ShopService.get_my_shop`，跨域 service 合法；无副作用；design Decision 4b/4c）
- [x] 3.3 `pay_order` 鉴权收编：router 改用 `get_current_order_for_buyer`，`OrderService.pay_order` 改收已鉴权 Order（去 buyer 校验；非买家 403→404，design Decision 4c 归属失败统一 404）
- [x] 3.4 `create_shipment` 鉴权收编：新增店主视角 deps（`get_current_order_for_shop`，内部吃 `ShopService.get_my_shop`），service 改收已鉴权 Order（非本店 403→404，design Decision 4c）
- [x] 3.5 读路径推翻 Phase B：router 用 `get_current_order_for_buyer_or_shop` 拿已鉴权 Order，`service.get_order_response(order)` 收实体**内部懒释放 + items 数据准备 + 映射**；`get_order_or_404` 私有化 `_get_order_or_404`
- [x] 3.6 `cancel_order` 补 self-expire（开头 `await self.expire_if_needed(order)`，仿 pay_order）——deps 纯化后不先触发懒释放，服务方法自含业务完整性（Decision 4c）；保留过期订单取消 409 语义
- [x] 3.7 `batch_pay` 保留 service 逐笔校验（多 order_ids，deps 单实体模式不适用；design Decision 8 documented；`batch_pay_orders` 已自含逐笔校验 + self-expire，无需改动）
- [x] 3.8 收尾：`devbox run -- task ci` 全绿（406 passed），`tests/ordering` integration 全绿（79 passed）

## 4. cart 域

- [x] 4.1 `CartService.update_qty` / `delete_item` 鉴权收编：新增 `get_current_cart_item` deps（解析 cart_item + 归属校验），service 收已鉴权实体
- [x] 4.2 `checkout` 保留 service 逐笔校验（多 cart_item_ids，deps 单实体模式不适用；design Decision 8 documented；`checkout` 已自含逐笔校验 + 单事务，无需改动）
- [x] 4.3 `get_checkout_batch` 鉴权收编：新增 `get_current_checkout_batch` deps（解析 batch + buyer 校验），service 收已鉴权 batch
- [x] 4.4 收尾：`devbox run -- task ci` 全绿（406 passed），`tests/ordering` cart 相关全绿

## 5. support 域

- [x] 5.1 新增 `ShopService.get_my_shop_context(owner_user_id) -> ShopContext`（返上下文 schema）；support/deps.py 新增 `get_current_support_shop(user_id)` deps **只转发**（不建 schema；design Decision 4b 跨域解析）
- [x] 5.2 店主路径升级：`list_inbox` / `get_inbox_conversation` / `list_inbox_messages` / `send_shop_message` 改经 `get_current_support_shop`，service 方法改收 `ShopContext`（**非 Shop ORM**，跨域禁 import ORM；design Decision 4b/4c），删除 `_get_current_shop_id` service 内自解析（注：实际店主路径 4 处，proposal "7 处"为早期盘点计数）
- [x] 5.3 买家路径（`get_shop_context` + `_ensure_not_owner`）确认保留 service 自解析（跨域解析 catalog shop，非本域；design Decision 8 documented；无改动）
- [x] 5.4 收尾：`devbox run -- task ci` 全绿（406 passed），`tests/support` integration 全绿

## 6. user 域

- [x] 6.1 user/deps.py 新增 `get_current_user` deps（本域仓储直读，返 User ORM）；`get_user_response` 改收 User 实体（推翻 Phase B service 内自解析）
- [x] 6.2 `update_profile` 确认保留：user_id 是业务参数（更新当前用户自己资料，get_by_id 读自身实体），非自解析鉴权；design Decision 8 documented；无改动
- [x] 6.3 收尾：`devbox run -- task ci` 全绿（406 passed），`tests/user` integration 全绿

## 7. AST lint 强制

- [ ] 7.1 新增 `scripts/check_app_layer_discipline.py`（Python AST）：`_*` 私有名不跨模块、跨域白名单（service/schemas/service-provider deps；current-object deps **禁跨域仓储/ORM、放行本域仓储直读**）、`get_current_*` 仅被本域 router 消费、**私有方法跨模块/跨域消费收编**（`cart_service → _create_order_core` 违规，design Decision 4c）
- [ ] 7.2 Taskfile 新增 `check-app-layer-discipline` task 并挂进 `task ci`（仿 `check-test-imports` 模式）
- [ ] 7.3 AST 脚本对 `app/` 全量跑通（放行域内、拦跨域违规）；启发式结构规则（薄 router / 上帝 service）降为警告或暂不启用
- [ ] 7.4 全 change 收尾：`devbox run -- task ci` 全绿（pytest 406 量级 + 新 lint gate 全过），`refactor-regression` spec 验证通过
