## 1. 文档与规范基线

- [x] 1.1 确认 `docs/troubleshooting/测试架构-旧模式反模式记录.md` 已含反模式代码片段、问题标注与迁移对照（非仅签名列表）
- [x] 1.2 新增 `.cursor/rules/test-architecture.mdc`（四层、PipelineResult、Case 禁令、fail-fast、反模式引用 troubleshooting 文档）

## 2. Support 层基础设施

- [x] 2.1 新增 `tests/support/pipeline.py`（或并入 `contexts.py`）：`PipelineResult`、`step()`、`all()`，精确 `type() is` 匹配
- [x] 2.2 新增 `ProductResult` 至 `tests/support/results.py`
- [x] 2.3 新增 `tests/support/projections.py`（或 `utils.py`）：`bearer_headers(result)` 纯函数
- [x] 2.4 新增 `tests/support/seeds.py`：迁移 `seed_inactive_user`（自 `test_login.py`）
- [x] 2.5 新增 `tests/support/helpers.py`：自 `conftest.py` 迁移原子 helper 与 orchestrator

## 3. Context 与 orchestrator 重构

- [x] 3.1 重构 `*Context` 为极薄 `root: PipelineResult`（`ShopOwnerContext`、`AdminAuthContext`、`AuthContext`）
- [x] 3.2 `register_and_open_shop` 改返 `PipelineResult`（不再返 `ShopOwnerContext`）
- [x] 3.3 新增 `login_admin` orchestrator → `PipelineResult(steps=(LoginResult,))`（或等价）
- [x] 3.4 新增 `create_product(client, *, shop_owner: PipelineResult, category: CategoryResult, ...) -> ProductResult`（不 assert 201）
- [x] 3.5 移除 helper 内成功 assert；移除 `_auth_context_from_register` 在 orchestrator 路径上的使用

## 4. Fixture 层（fail-fast）

- [x] 4.1 重构 `authenticated_user`、`shop_owner`、`admin_auth_headers` fixture：调 orchestrator → fail-fast → `*Context(root=...)`
- [x] 4.2 精简 `tests/conftest.py`：保留 session/client/db fixture 与 re-export；helper 实现迁至 `helpers.py`
- [x] 4.3 更新 `conftest.__all__` 与 import 路径

## 5. Catalog 测试迁移

- [x] 5.1 删除 `test_create_product.py` 内 `_create_*` helper；改用 support `create_product` / `create_category`
- [x] 5.2 移除 `test_public_products.py`、`test_my_products.py`、`test_update_product.py` 对 `test_create_product` 的 cross-import
- [ ] 5.3 迁移 catalog 断言路径：`shop_owner.shop` → `shop_owner.root.step(ShopResult)` 等；Act 保持可见
- [ ] 5.4 补全 catalog integration tests 的 `client: AsyncClient` 等类型注解

## 6. User 测试迁移

- [ ] 6.1 迁移 `test_login.py`：使用 `seed_inactive_user` from support；移除 test 内 helper
- [ ] 6.2 迁移 user tests Context/Result 访问路径与类型注解
- [ ] 6.3 确认失败登录/注册 Case 仍 inline 调 helper 断言（无失败 fixture）

## 7. 目录与 ops 探针

- [ ] 7.1 创建 `tests/ops/` 并迁移 `test_health.py`、`test_readiness.py`、`test_migration_smoke.py`
- [ ] 7.2 添加 `tests/ops/__init__.py`；确认 pytest 收集路径正常

## 8. Enforcement

- [ ] 8.1 `pyproject.toml`：对 `tests/` 启用 ruff ANN 规则
- [ ] 8.2 Taskfile/CI：grep 禁止 `from tests.<domain>.test_` 互 import
- [ ] 8.3 `uv run ruff check .` 与 grep 脚本本地验证

## 9. 验证与归档准备

- [ ] 9.1 `devbox run -- task ci` 全绿（测试场景与断言语义不变）
- [ ] 9.2 审查无 test 内可复用 helper、无 test 互 import、无 helper 返 Context
- [ ] 9.3 archive 时 sync `openspec/specs/test-architecture/` 与 `openspec/specs/integration-test-typing/`