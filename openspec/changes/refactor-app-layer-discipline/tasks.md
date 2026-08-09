## 1. 规范成文

- [ ] 1.1 新增 `.cursor/rules/app-layer-discipline.mdc`：deps 两大类（装配/解析）、业务不进 deps、跨域白名单两维（service 接口 + schemas）、service 双形态（返 schema / 返 ORM）、域内 current-object 模式（`get_current_*` 只被本域 router 消费）、`_*` 私有名不跨模块
- [ ] 1.2 新增 `docs/decision/ADR-010-应用层边界纪律.md`：决策 + 理由 + 四反模式对照 + 推翻 B/D 的说明
- [ ] 1.3 增补 `docs/architecture.md` §4 域间协作规则：deps 两大类、跨域白名单、service 双形态、域内 current-object 模式
- [ ] 1.4 更新 `docs/troubleshooting/deps-跨域两步与上帝service反模式.md` 的"规范对照"链接指向本 change 决策

## 2. catalog 域

- [ ] 2.1 `ShopService` 新增 `get_shop_or_404(owner_user_id) -> Shop`（返 ORM，供 current-object deps）；`get_current_shop` 改吃 `get_shop_service`，不再直吃 `get_shop_repository`
- [ ] 2.2 catalog/deps.py 新增 `get_current_product(product_id, user_id) -> Product`（解析 product 404 + product 归属 shop 校验）；`ProductService.update_product` 改收已鉴权实体（去 self 自解析鉴权），router 改用 `get_current_product`
- [ ] 2.3 删除 `get_current_shop` 的 repository 直连残留；验证 catalog 域内 import 全部合规（域内 models/repository 允许，跨域白名单不误伤）
- [ ] 2.4 收尾：`devbox run -- task ci` 全绿，`tests/catalog` integration 全绿

## 3. ordering 域

- [ ] 3.1 ordering/deps.py 命名统一：`get_order_by_id` → `get_current_order`、`get_order_for_buyer` → `get_current_order_for_buyer`、`get_order_for_buyer_or_shop` → `get_current_order_for_buyer_or_shop`；同步所有 router `Depends` 引用
- [ ] 3.2 `pay_order` 鉴权收编：router 改用 `get_current_order_for_buyer`，`OrderService.pay_order` 改收已鉴权 Order（去 buyer 校验）
- [ ] 3.3 `create_shipment` 鉴权收编：新增店主视角 deps（`get_current_order_for_shop`，内部吃 `ShopService.get_my_shop`），service 改收已鉴权 Order
- [ ] 3.4 读路径 `get_order_response(order_id, user_id)` 推翻 Phase B：router 用 `get_current_order_for_buyer_or_shop` 拿已鉴权 Order，service 改收 Order 只做映射
- [ ] 3.5 `batch_pay` 保留 service 逐笔校验（多 order_ids，deps 单实体模式不适用；design Decision 8 documented）
- [ ] 3.6 收尾：`devbox run -- task ci` 全绿，`tests/ordering` integration 全绿

## 4. cart 域

- [ ] 4.1 `CartService.update_qty` / `delete_item` 鉴权收编：新增 `get_current_cart_item` deps（解析 cart_item + 归属校验），service 收已鉴权实体
- [ ] 4.2 `checkout` 保留 service 逐笔校验（多 cart_item_ids，deps 单实体模式不适用；design Decision 8 documented）
- [ ] 4.3 `get_checkout_batch` 鉴权收编：新增 `get_current_checkout_batch` deps（解析 batch + buyer 校验），service 收已鉴权 batch
- [ ] 4.4 收尾：`devbox run -- task ci` 全绿，`tests/ordering` cart 相关全绿

## 5. support 域

- [ ] 5.1 support/deps.py 新增 `get_current_support_shop(user_id)` deps（本域 deps 吃 catalog `ShopService.get_my_shop`，跨域 service 调合法）
- [ ] 5.2 7 处店主路径升级：`list_inbox` / `get_inbox_conversation` / `list_inbox_messages` / `send_shop_message` 改经 `get_current_support_shop`，service 方法改收 Shop 实体，删除 `_get_current_shop_id` service 内自解析
- [ ] 5.3 买家路径（`get_shop_context` + `_ensure_not_owner`）确认保留 service 自解析（跨域解析 catalog shop，非本域；design Decision 8 documented）
- [ ] 5.4 收尾：`devbox run -- task ci` 全绿，`tests/support` integration 全绿

## 6. user 域

- [ ] 6.1 user/deps.py 新增 `get_current_user` deps（返 User ORM）；`get_user_response` 改收 User 实体（推翻 Phase B service 内自解析）
- [ ] 6.2 `update_profile` 确认保留：user_id 是业务参数（更新当前用户自己资料，get_by_id 读自身实体），非自解析鉴权；design Decision 8 documented
- [ ] 6.3 收尾：`devbox run -- task ci` 全绿，`tests/user` integration 全绿

## 7. AST lint 强制

- [ ] 7.1 新增 `scripts/check_app_layer_discipline.py`（Python AST）：`_*` 私有名不跨模块、跨域白名单（service/schemas/service-provider deps）、`get_current_*` 仅被本域 router 消费
- [ ] 7.2 Taskfile 新增 `check-app-layer-discipline` task 并挂进 `task ci`（仿 `check-test-imports` 模式）
- [ ] 7.3 AST 脚本对 `app/` 全量跑通（放行域内、拦跨域违规）；启发式结构规则（薄 router / 上帝 service）降为警告或暂不启用
- [ ] 7.4 全 change 收尾：`devbox run -- task ci` 全绿（pytest 406 量级 + 新 lint gate 全过），`refactor-regression` spec 验证通过
