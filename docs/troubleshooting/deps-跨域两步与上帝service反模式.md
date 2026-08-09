# deps 跨域两步与上帝 service — 反模式记录

> **状态**：`refactor-app-layer-boundaries` 分支闭环后留档（跨域两步 + 上帝 service 已修复）。
> **目的**：用真实代码说明「错在哪、为什么错」；对照修复方向，新代码不得延续这些模式。
> **背景**：这些反模式是**规范缺失下 AI 引入的随机性**——工程纪律未成文前，AI 在 deps / service / router 分层边界上做了任意取舍，小违规悄然累积成架构侵蚀（破窗效应）。
> **规范对照**：修复决策见 `openspec/changes/refactor-app-layer-boundaries/design.md`（Decision 2 / Decision 7）；规范全文留给 `docs-app-layer-discipline`。
> **日期**：2026-08-09

---

## 反模式索引

| #   | 类         | 反模式                              | 典型位置（修复前）                                      | 修复手段                                            |
| --- | -------- | --------------------------------- | ------------------------------------------- | ---------------------------------------------- |
| ①   | 跨域调用 | deps 建 schema                     | `get_order_for_buyer_or_shop_response` / `get_current_user` | service 公开读方法产 schema，`_to_*` 保持私有       |
| ②   | 跨域调用 | deps 跨域调用                       | support `Depends(get_current_shop)`（catalog deps）    | 业务收进 service，经已注入 service 解析本店            |
| ③   | 跨域调用 | 跨域两步调用（service `get_xxx` + router 两步串联） | support `get_current_shop_id` → `list_inbox`；cart checkout-batch router 编排 | service 业务方法自解析、一步完成                     |
| ④   | 域内膨胀 | 上帝 service → 上帝 deps            | 单一 `ShopService` 包 shop/category/product/库存/跨域读 | 按实体拆 service + 按端点分窄 deps                   |

> 归类脉络：①②③ 是**跨域调用**问题（1 给 2 铺路，2 诱发 1；3 是解决 2 后的 workaround）；④ 是**域内膨胀**问题（service 管理偷懒）。

---

## 反模式 ①：deps 建 schema（deps 承担业务输出）

### 错在哪

deps 的本职是**装配**与**纯横切鉴权**（解析请求上下文）。当 deps 开始用 `_to_*` 构建对外 schema 时，deps 越过了 service 边界、承担业务输出，成为「第二个 schema 出口」——schema 的权威定义从 service 漂移到 deps。

### 案例（Phase B 修复前）

```python
# ordering/deps.py：deps 读路径构建 OrderResponse
async def get_order_for_buyer_or_shop_response(order, user_id, ...) -> OrderResponse:
    ...
    return _to_order_response(order)   # ❌ deps 调 service 私有映射建 schema

# user/deps.py：deps 构建 UserResponse
async def get_current_user(user_id, ...) -> UserResponse:
    ...
    return _to_user_response(user)     # ❌ 同上
```

### 应怎么做

- 读路径 schema 由 **service 公开方法**产出：`OrderService.get_order_response(order_id, user_id)` / `UserService.get_user_response(user_id)`（fetch → 404 → 懒释放 → 鉴权 → 私有 `_to_*`）。
- deps 只保留装配 + 纯鉴权 gate（`get_current_user_id` / `require_admin`）。

---

## 反模式 ②：deps 跨域调用（跨域接线越过 service）

### 错在哪

deps 一旦被跨域消费，deps 就成了「域公共面」，诱发 ①（跨域方借 deps 拿 schema）。跨域协作必须只走 **service 接口 + schema**；deps 是本域私有装配。

### 案例（Phase B 修复前）

```python
# support/router.py：跨域使用 catalog 的 current-object deps
async def inbox_list(
    user_id=Depends(get_current_user_id),
    shop: Shop = Depends(get_current_shop),   # ❌ 跨域 import catalog deps
    ...
): ...
```

### 应怎么做

- `get_current_shop` 退回 **catalog 域内私有**（仅 catalog router 消费）。
- support 店主路径改为注入 `user_id` + 已注入的 `ShopService.get_my_shop(user_id)` 解析本店（404 语义一致）。

---

## 反模式 ③：跨域两步调用（service `get_xxx` + router 两步串联）

### 错在哪

Phase B 禁跨域 deps 后，跨域上下文靠 router 两步串联：`shop_id = await service.get_current_shop_id(user_id)` 再 `service.list_inbox(shop_id, ...)`。router 承担了不该承担的**编排**；跨域上下文必须由 service 业务方法自解析、一步完成。同域 current-object deps（`get_current_shop` / `get_order_*`）是合法 FastAPI 惯用法，保留——真正的反模式是**跨域两步**。

### 案例（Phase D 修复前）

```python
# support/router.py：两步调用
shop_id = await service.get_current_shop_id(user_id)      # 第一步：解析本店
return await service.list_inbox(shop_id, ...)             # 第二步：业务调用

# ordering/cart_router.py：checkout-batch 端点整段编排
orders = await order_repo.list_by_checkout_batch_id(batch_id)
for order in orders:
    await order_service.expire_if_needed(order)           # 跨入 OrderService
    ...
    items = await order_service._item_repo.list_by_order_id(...)  # ❌ 私有访问
...
status=_derive_batch_status(statuses)                     # router 计算派生状态
```

### 应怎么做

- service 业务方法**收 `user_id` 自解析**：`list_inbox(user_id, ...)` 内部经私有 `_get_current_shop_id`；router 一步调用。
- 编排收进 service：`CartService.get_checkout_batch(batch_id, user_id)`（fetch/404/子订单/聚合/派生状态/build schema 全收编）；OrderService 暴露 `list_orders_by_checkout_batch`（方案 A）；`_derive_batch_status` 迁入 service；消除 `order_service._item_repo` 私有访问。

---

## 反模式 ④：上帝 service → 上帝 deps（域内膨胀）

### 错在哪

单一 service 类承担多实体职责，迫使 `get_*_service()` 一次注入多个 repo + 跨域 service；跨域调用方被迫依赖整个上帝类。service 越界导致 **deps 上帝化**（反模式 ④：上帝 service → 上帝 deps）。

### 案例（Phase C 修复前）

```python
# catalog/service.py：单一 ShopService 包 shop/category/product/库存/跨域读 facade
class ShopService:
    def __init__(self, shop_repo, category_repo, product_repo, media_service, ...): ...
    # create_category / list_categories / create_product / reserve_stock /
    # get_purchasable_products / get_products_for_engagement / ... 全在一个类

# catalog/deps.py：为塞进上帝类，一次注入三 repo + media
def get_shop_service(shop_repo, category_repo, product_repo, media_service) -> ShopService: ...
```

### 应怎么做

- 按实体拆 service：`CategoryService` / `ProductService` / `ShopService`；deps 分设 `get_category_service()` / `get_product_service()` / `get_shop_service()`，各注入所需 repo。
- 跨域调用方改 **narrow** 注入：ordering / engagement / support 只依赖 `ProductService` + 必要的 `ShopService`，不再依赖整个上帝类。
- **踩坑**：上帝 service 拆开时 blast radius 全局——同一 deps 入口被多域复用，收窄一个 service 牵动所有调用方的注入与构造签名。

---

## 元教训：规范缺失下 AI 引入的随机性

- 上述四反模式不是「某个 bug」，而是**工程纪律未成文时 AI 的随机选择**：deps 建 schema 还是 service 建 schema？跨域走 deps 还是 service？跨域上下文由 router 两步串还是 service 一步收？service 拆细还是堆上帝类？——每个都是二选一，AI 每次随意选边，累积成架构侵蚀。
- 修复方向（design.md Decision 2/7 定稿）：**跨域只走 service + schema；deps 只留装配 + 纯横切鉴权；同域 current-object deps 合法保留；service 按实体拆、deps 按端点分窄；跨域上下文 service 一步自解析**。
- 规范全文（MUST）留给 `docs-app-layer-discipline`——只有把「为什么」成文，才能消除后续 AI 的随机性。

---

## 迁移对照（修复前 → 修复后）

| 反模式 | 修复前 | 修复后 |
|--------|--------|--------|
| ① deps 建 schema | `get_order_for_buyer_or_shop_response` / `get_current_user` 返 schema | `OrderService.get_order_response` / `UserService.get_user_response` |
| ② deps 跨域 | support `Depends(get_current_shop)` | `user_id` + `ShopService.get_my_shop` |
| ③ 跨域两步 | support `get_current_shop_id` 两步；cart checkout-batch router 编排 + `_item_repo` 私有访问 | `list_inbox(user_id, ...)` 一步；`CartService.get_checkout_batch` + `OrderService.list_orders_by_checkout_batch` |
| ④ 上帝 service | 单一 `ShopService` + 上帝 `get_shop_service()` | `CategoryService` / `ProductService` / `ShopService` + 分窄 deps |
