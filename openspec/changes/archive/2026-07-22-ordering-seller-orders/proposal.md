## Why

`ordering-buyer-orders` 已交付买家发起订单与整条交易闭环（付桩、发货、收货、取消），但**卖家无法为沟通对象开单**，无法支撑未来 IM 场景下的「商家报价 → 买家支付确认」路径。本 change 在不变更 FSM 的前提下，补齐**卖家发起建单**能力，并引入跨域用户摘要查询，使买卖双方均能在各自列表中看到对方发起的待支付订单。

## What Changes

- **卖家建单**：`POST /shops/me/orders`（需认证，仅店主）；body `{ "buyer_user_id", "items": [...] }` → `status=awaiting_payment`、`initiated_by=seller`；库存预留/快照规则与买家建单相同
- **买家建单补字段**：现有 `POST /orders` 写入 `initiated_by=buyer`；`OrderResponse` 暴露 `initiated_by`
- **数据模型**：`orders.initiated_by`（`buyer` | `seller`）；migration `006` 回填已有行为 `buyer`
- **跨域 user**：`user.service.get_user_summary(user_id)` → `UserSummary`（`id` + `nickname`）；买家不存在 **404**；`is_active=false` **422**
- **确认语义**（无新状态）：买家发起 → pay 时卖家隐式确认；卖家发起 → 建单即卖家确认，pay 即买家确认 → 均进入 `confirmed`
- **可见性**：买家建单后店主 `GET /shops/me/orders` 可见；卖家建单后指定买家 `GET /orders` 可见
- **懒释放增强**：`GET /shops/me/orders` 与 `GET /orders` 对列表中 `awaiting_payment` 订单**逐单** `expire_if_needed`（仍无周期扫描 / Redis / MQ）
- **业务规则延续**：禁自购（卖家指定 `buyer_user_id` 不得为店主本人）；店 `closed` / 未上架 / 跨店 / 库存不足 → **422**；卖家不得 pay / confirm-receipt
- 扩展 **pytest**：`tests/ordering/` 覆盖卖家/买家双路径建单与列表可见性

## Non-goals

- 不实现 IM / 聊天、用户搜索 API
- 不扩展 `UserSummary` 为 email、地址、联系方式（留待物流/用户资料 change）
- 不实现真实支付、物流、退货、`completed` 后取消
- 不引入 Redis、MQ、周期扫描自动释放
- 不统一 HTTP 403/404 或 PATCH 发货命名（留待后续 API 规范 change）
- 不实现购物车、跨店合单、一人多店

## Capabilities

### New Capabilities

- `ordering-seller-orders`：卖家为指定买家建单、`initiated_by=seller`、跨域校验买家用户摘要

### Modified Capabilities

- `ordering-buyer-orders`：`initiated_by` 列与响应字段；买家建单写 `buyer`；列表路径逐单懒释放
- `user-auth`：跨域只读 `UserSummary` + `get_user_summary` service 方法（ordering 校验买家存在且 active）

## Impact

- **业务域**：`ordering`（router/service/model/schemas/repository）、`user`（service/schemas）、`infra`（Alembic `006`）
- **新增/修改**：`app/ordering/*`、`app/user/service.py` + `schemas.py`、`alembic/versions/006_*.py`、`tests/ordering/`、`tests/support/` helpers
- **API**：新增 `POST /shops/me/orders`；`OrderResponse` 增加 `initiated_by`；列表行为增强
- **分支**：基于 `dev` 的 `feature/ordering-seller-orders`
