## 1. TDD — 失败测试（红）

- [x] 1.1 扩展 `tests/support/`（遵循 test-architecture 四层）：
  - `helper/engagement.py` 原子 HTTP helper（返回 `*Result`，不 assert 成功）：`add_favorite`、`delete_favorite`、`list_favorites`、`batch_delete_favorites`
  - `results.py`：FavoriteResult、FavoriteListResult、BatchDeleteFavoritesResult
  - 复用既有 `arrange_purchasable_product` / catalog seed 编排场景
- [x] 1.2 编写 `tests/engagement/test_favorites_crud.py`（POST 201/200 幂等、422 不存在、DELETE 204/404、401）；不编写实现
- [x] 1.3 编写 `tests/engagement/test_favorites_list.py`（GET 空列表、items/unavailable_items 分类、reason 枚举、分页 total、created_at 降序、未上架可 POST）；不编写实现
- [x] 1.4 编写 `tests/engagement/test_favorites_batch_delete.py`（batch-delete 子集删除、跳过未收藏 id、422 空列表、401）；不编写实现
- [x] 1.5 `devbox run -- task db:up` 后跑新增 engagement 测试，确认失败（红）

## 2. catalog 跨域扩展（repository 复用 + EngagementProduct）

- [x] 2.1 `ProductRepository.fetch_products_with_shop_by_ids`：从既有 `get_purchasable_products` SQL 抽取；`get_purchasable_products` refactor 为调用共用方法（行为不变）
- [x] 2.2 `EngagementProduct` schema + `ShopService.get_products_for_engagement`；补充 `image_url` 字段映射
- [x] 2.3 跑 `tests/ordering/` 与 catalog 相关测试，确认 refactor 无回归
- [x] 2.4 `tests/unit/catalog/` 新增 `get_products_for_engagement` 字段映射单测（EngagementProduct 全字段、price 字符串化、image_url 保留/None、不过滤上架/店状态、shop_active 推导、空结果返回 []、不存在 id 不出现）

## 3. 迁移与 engagement ORM（绿 · 基础）

- [x] 3.1 新增 `app/engagement/models.py`（`UserFavorite`）；`alembic/env.py` 导入
- [x] 3.2 新增 migration `009`：`user_favorites` 表及 `UNIQUE(user_id, product_id)`、索引

## 4. engagement 实现（绿）

- [x] 4.1 `repository.py` + schemas（FavoriteItem、UnavailableFavoriteItem、FavoriteListResponse、BatchDeleteFavoritesRequest/Response 等）
- [x] 4.2 `FavoriteService`：POST/DELETE、`_classify_favorites`、list + batch_delete；注入 `ShopService`
- [x] 4.3 `deps.py` + `router.py`（/favorites*）；`main.py` 挂载
- [x] 4.4 跑 engagement 测试至全绿

## 5. 文档与 CI

- [x] 5.1 更新 `docs/architecture.md`（engagement 域、user_favorites、API 摘要）
- [x] 5.2 `devbox run -- task ci` 全绿
