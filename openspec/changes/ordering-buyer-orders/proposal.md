## Why

`user` 认证与 `catalog`（店铺 / 类目 / 商品）已交付，但仍无订单，无法形成「上架 → 下单 → 成交 → 发货 → 收货」的交易闭环，项目尚达不到可演示最小单元。需要在 `ordering` 域交付**买家发起**的订单垂直切片（支付桩、库存预留、履约状态），为后续卖家开单与真支付/物流留扩展点。

## What Changes

- 新增 **ordering 域**（`app/ordering/`）：router → service → repository → model + schemas
- 表（ordering 域，migration `005`）：`orders`、`order_items`
- **买家下单**：`POST /orders`（一店多行）；创建时快照行上 `product_name` / `unit_price` / `qty`；`status=awaiting_payment`；`expires_at`；**单字段扣减库存**（条件更新防超卖）
- **支付桩**：`POST /orders/{id}/pay`（永远成功；未过期且状态合法时 → `confirmed`）
- **发货**：`POST /orders/{id}/shipments`（本店卖家；body `{}` 或可选 `note` → `shipped`）
- **确认收货**：`POST /orders/{id}/confirm-receipt`（买家 → `completed`）
- **取消**：`POST /orders/{id}/cancel`（买家或本店卖家；`awaiting_payment` / `confirmed` / `shipped` 可取消 → `cancelled` + `cancel_reason`；**`completed` 禁止**）
- **超时**：并入 `cancelled` + `cancel_reason=expired`；本 change **仅懒释放**（pay / 下单 / 读单等路径检查 `expires_at`），无 Redis、无 MQ、无周期扫描
- **查询**：买家 `GET /orders`、`GET /orders/{id}`；卖家 `GET /shops/me/orders`
- **跨域**：ordering 仅调用 `catalog.service` 预留/释放库存与读取可购商品信息；禁止 import `catalog.models` / repository
- **业务规则**：仅 `is_published` 且店铺 `active` 可下单；**禁止店主购买本店商品**；多行须同店；非法状态迁移 → **409**
- 扩展 **pytest**：`tests/ordering/` integration（对齐四层测试架构）
- 更新 **README.md** / **docs/architecture.md**（订单状态机、预留 TTL）

## Non-goals

- 不实现卖家发起订单（下一 change）
- 不实现真实支付渠道、退款、退货售后
- 不实现物流轨迹 / 运单号必填 / `in_transit` 等子状态
- 不引入 Redis、MQ、Celery；不做周期扫描自动释放（仅懒释放）
- 不实现购物车、跨店合单、地址簿、运费
- 不在本 change 做 `completed` 后取消

## Capabilities

### New Capabilities

- `ordering-buyer-orders`：买家发起订单、支付桩、库存预留与懒释放超时、发货（shipments）、确认收货、买卖双方取消（除 completed）、买家/卖家订单查询

### Modified Capabilities

- `catalog-products`：新增供 ordering 调用的库存预留/释放与可购校验相关 **service + schema**（条件更新 `stock`；跨域禁止 ORM）

## Impact

- **业务域**：`ordering`（新建）、`catalog`（service/schemas/repository 库存写路径）、`infra`（TTL 等配置项）
- **新增/修改**：`app/ordering/*`、`app/catalog/service.py`（及必要 repository/schemas）、`alembic/versions/005_*.py`、`app/main.py` 挂载路由、`tests/ordering/`、`tests/support/`（订单相关 helpers）、`README.md`、`docs/architecture.md`
- **API**：新增 `/orders*`、`/shops/me/orders`、`/orders/{id}/pay|shipments|confirm-receipt|cancel`
- **分支**：基于 `dev` 的 `feature/ordering-buyer-orders`
