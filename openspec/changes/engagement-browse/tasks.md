## 1. TDD — 失败测试（红）

- [ ] 1.1 扩展 `tests/support/`：
  - `helper/engagement.py` 追加原子 HTTP helper：`record_browse`、`list_browse`、`delete_browse`（返回 `*Result`）
  - `results.py`：BrowseAcceptedResult、BrowseListResult
  - helper 内 await BackgroundTasks 完成后再返回（或提供 `flush_background_tasks` fixture）
- [ ] 1.2 编写 `tests/engagement/test_browse_record.py`（POST 202、422 不存在、401、debounce 不 +1、view_count 递增/重置、await DB）；不编写实现
- [ ] 1.3 编写 `tests/engagement/test_browse_list.py`（GET 空列表、items/unavailable_items 分类、reason 枚举、分页 total、last_viewed_at 降序）；不编写实现
- [ ] 1.4 编写 `tests/engagement/test_browse_delete.py`（DELETE 204/404、401）；不编写实现
- [ ] 1.5 编写 `tests/unit/engagement/test_trim_browse_history.py`（top N 内超 retention 保留、top N 外超 retention 删除；使用 `.env.test` 小 MAX）；不编写实现
- [ ] 1.6 `devbox run -- task db:up` 后跑新增 browse 测试，确认失败（红）

## 2. 配置与 infra

- [ ] 2.1 `app/infra/config.py` 新增 `browse_history_max_per_user`、`browse_history_retention_days`、`browse_debounce_seconds`
- [ ] 2.2 更新 `.env.example`（50/30/5）与 `.env.test`（3/30/5）

## 3. 迁移与 engagement ORM（绿 · 基础）

- [ ] 3.1 `app/engagement/models.py` 追加 `UserBrowseHistory`；`alembic/env.py` 已导入 engagement models
- [ ] 3.2 新增 migration `010`：`user_browse_history` 表、`UNIQUE(user_id, product_id)`、索引

## 4. Trim job（绿 · unit）

- [ ] 4.1 `app/engagement/jobs/trim_browse_history.py`：纯函数 + `async` session 入口 + `__main__` CLI
- [ ] 4.2 `Taskfile.yml` 新增 `browse:trim`
- [ ] 4.3 跑 trim unit 测试至全绿

## 5. engagement browse 实现（绿）

- [ ] 5.1 `repository.py` 追加 BrowseRepository；schemas（BrowseItem、UnavailableBrowseItem、BrowseListResponse、BrowseRecordRequest、BrowseAcceptedResponse）
- [ ] 5.2 `BrowseService`：POST 校验 + `record_browse_async`（upsert/debounce/view_count）、`_classify_browses`、list、delete；注入 `ShopService`
- [ ] 5.3 `deps.py` + `router.py` 追加 `/browse*`（BackgroundTasks）；无需改 `main.py`（同 engagement router）
- [ ] 5.4 跑 browse integration 测试至全绿

## 6. 文档与 CI

- [ ] 6.1 更新 `docs/architecture.md`（engagement 浏览、`/browse*` API、trim job 摘要）
- [ ] 6.2 `devbox run -- task ci` 全绿（含 trim unit + browse integration）
