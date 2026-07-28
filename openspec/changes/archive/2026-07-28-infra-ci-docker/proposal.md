## Why

电商 MVP 功能已在 `dev` 交付（user / catalog / ordering），但 CI 仍为单一 job 跑完全部测试、无依赖缓存与测试报告；架构文档 §8.3 规划的 **Docker 镜像构建** 尚未落地。`dev` 领先 `main` 约 150+ commits，即将以 **v1.0.0** 合流 main 并进入可部署阶段。现需在 `infra-cd-compose`（Push 部署）之前，先完善 **Validate（lint + 域并行测试 + Allure）** 与 **Build（多阶段镜像 → GHCR）**，为 v1.0.0 发布提供工程基线。

## What Changes

- **CI 拆分与加速**：lint job 独立；test job 按域 **matrix 并行**（user / catalog / ordering / infra+ops / unit）；`workflow_dispatch` 增加 `domain` 输入筛选单域或全量
- **uv 依赖缓存**：GitHub Actions cache `~/.cache/uv`（key 绑定 `uv.lock`）
- **Allure 测试报告**：`allure-pytest`；本地 `reports/`（gitignore）；Taskfile 新增 `test:reports`、`latest:report`；CI 每 matrix job upload `allure-results` artifact
- **Allure 层级**：各测试用 `@allure.epic`（域）+ `@allure.feature`（场景）+ `@allure.title`（Story 中文标题，从现有 docstring/测试名迁移）
- **域测试本地入口**：Taskfile 新增 `test:user` / `test:catalog` / `test:ordering` / `test:infra` / `test:unit`（路径筛选，不新增 pytest domain marker）
- **多阶段 Dockerfile**：仅 app + 生产依赖（不含 MySQL/Redis/tests）；CMD `uvicorn`
- **镜像构建 workflow**：push **`main`** 或 **版本 tag**（`v*`）触发 build + push **GHCR**；PR/feature 分支不 build
- **版本策略文档**：v1.0.0 = 电商底座首次 release；v1.x.0 = 底座完善；v2.0.0 = AI 平台（后续）
- 更新 **README.md**、**docs/architecture.md** §8.3

## Non-goals

- **不** 实现 CD 部署（SSH、docker-compose 生产编排）—— 留给后续 `infra-cd-compose` change
- **不** 引入 K8s、GitOps（ArgoCD/Flux）、cosign 镜像签名
- **不** 本地 docker-compose 替代 devbox MySQL/Redis（与 ADR-002 一致）
- **不** 修改业务域 API、迁移或运行时行为
- **不** 引入 CodeQL/SonarQube 等静态分析、Dependabot/release-please 等仓库自动化
- **不** 在 PR 上默认 build 镜像（仅 main + tag）
- **不** 将 MySQL/Redis 打入 app 镜像

## Capabilities

### New Capabilities

- `infra-ci`: CI workflow 域 matrix、uv cache、workflow_dispatch 域筛选、Allure artifact、Taskfile 域测试与报告命令
- `infra-docker`: 多阶段 Dockerfile、GHCR push workflow、main/tag 触发策略、构建时 `/health` 烟雾验证

### Modified Capabilities

- `test-architecture`: 集成测试 SHALL 支持 Allure epic/feature/title 报告层级约定；新增 `reports/` 本地输出纪律

## Impact

- **业务域**: 仅 **infra** + **tests**（Allure 装饰器与 title，无业务逻辑变更）
- **新增/修改文件**: `.github/workflows/ci.yml`、`.github/workflows/docker-build.yml`（新）、`Dockerfile`、`.dockerignore`、`Taskfile.yml`、`pyproject.toml`（`allure-pytest` dev 依赖）、`.gitignore`、`tests/**/*.py`（Allure 装饰器）、`README.md`、`docs/architecture.md`
- **API**: 无业务 REST 变更
- **依赖**: dev 组 `allure-pytest`；本地可选 Allure CLI（`allure serve`/`open`，用于 `test:reports` / `latest:report`）
- **Registry**: `ghcr.io/<owner>/e-commerce-system`（tag 与 git semver 对齐，如 `v1.0.0`）
- **环境**: CI matrix 各 job 仍依赖 mysql + redis services + migrate；与现有 discipline 一致
