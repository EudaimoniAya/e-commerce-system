## 0. 测试脚本清理

- [x] 0.1 删除 `scripts/*_curl_smoke.sh`（与 pytest integration 重复；业务主流程由 `task ci` / 域测试覆盖）
- [x] 0.2 更新 README、`docs/architecture.md`、`test-architecture` spec 与 cursor rule：禁止新增重复 curl 烟雾脚本

## 1. 依赖与基础配置

- [x] 1.1 `pyproject.toml` dev 组添加 `allure-pytest`；`uv sync`
- [x] 1.2 `.gitignore` 添加 `reports/`；确认不跟踪 Allure 输出
- [x] 1.3 Taskfile 新增域测试任务：`test:user`、`test:catalog`、`test:ordering`、`test:infra`、`test:unit`（路径与 design matrix 一致）

## 2. Allure 本地报告命令

- [x] 2.1 Taskfile 新增 `test:reports`（deps `db:up` + `redis:up`；pytest `--alluredir=reports/allure-results`；`allure generate` → `reports/allure-report`）
- [x] 2.2 Taskfile 新增 `latest:report`（检查目录存在 → `allure open reports/allure-report`）
- [x] 2.3 README 补充 Allure CLI 安装说明、`test:reports` / `latest:report` 用法

## 3. Allure 装饰器 — user 域

- [ ] 3.1 `tests/user/` 全部 Case 添加 `@allure.epic("user")`、`@allure.feature(...)`、`@allure.title(...)`（从 docstring/测试名 cv）

## 4. Allure 装饰器 — catalog 域

- [ ] 4.1 `tests/catalog/` 全部 Case 添加 Allure 装饰器（epic=`catalog`）

## 5. Allure 装饰器 — ordering 域

- [ ] 5.1 `tests/ordering/` 全部 Case 添加 Allure 装饰器（epic=`ordering`）

## 6. Allure 装饰器 — infra / ops / unit

- [ ] 6.1 `tests/infra/`、`tests/ops/` 添加装饰器（epic=`infra` 或 `ops`）
- [ ] 6.2 `tests/unit/` 添加装饰器（epic=`unit`）

## 7. CI workflow 重构

- [ ] 7.1 拆分 `ci.yml`：`lint` job（ruff + check-test-imports，无 services）
- [ ] 7.2 `test` job：matrix domain（user/catalog/ordering/infra/unit）；每 job services + migrate + pytest `--alluredir=allure-results`
- [ ] 7.3 添加 uv cache（`~/.cache/uv`，key 绑定 `uv.lock`）
- [ ] 7.4 每 matrix job upload artifact `allure-results-<domain>`
- [ ] 7.5 `workflow_dispatch` 输入 `domain`（all/user/catalog/ordering/infra/unit）

## 8. Docker 镜像

- [ ] 8.1 编写多阶段 `Dockerfile` + `.dockerignore`（仅 app + 生产依赖）
- [ ] 8.2 新增 `.github/workflows/docker-build.yml`：触发 main push + `v*` tag；build + push GHCR；`/health` 烟雾
- [ ] 8.3 workflow `permissions: packages: write`；镜像 tag：`latest`、semver、`sha-*`

## 9. 文档与版本策略

- [ ] 9.1 更新 `docs/architecture.md` §8.3（Validate/Build 已实现；Deploy 留给 infra-cd-compose）
- [ ] 9.2 README 补充：域测试命令、CI matrix、GHCR 镜像、semver（v1.0.0 / v1.x / v2.0）

## 10. 本地验证与 CI

- [ ] 10.1 `devbox run -- task db:up` + `redis:up` 后 `devbox run -- task ci` 全绿；`task test:reports` + `latest:report`  smoke
- [ ] 10.2 push feature 分支；`workflow_dispatch` 验证单域 + 全 matrix + lint
- [ ] 10.3 确认远程 CI 全绿；更新 tasks.md 勾选

## 11. DoD

- [ ] 11.1 确认 DoD（本地 + 远程 CI）；可执行 `/opsx:archive`

> **Apply 约定**：§0（curl 脚本清理，已完成）→ §1–2 → §3–6（Allure 装饰器，按域分批 commit）→ §7–8（CI + Docker）→ §9–11。DB/Redis 使用 `devbox run --`。合入 main 后打 `v1.0.0` tag 触发首次镜像 build（本 change 合 dev 后由 dev→main PR 完成）。
