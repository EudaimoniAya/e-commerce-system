# ADR-006：CI 工作流与镜像发布策略

- **状态**：已采纳
- **日期**：2026-07-30
- **背景**：`infra-ci-docker`（已 archive）交付的 CI 使用 5 路 domain matrix 并行 pytest，且 PR/push 无路径筛选——文档、openspec 等变更仍会触发完整 lint + test。Build workflow 在 `main` push 与 `v*` tag 双触发，镜像 tag 含 `latest`/`sha-*` 等浮动标签，与「main 为可演示基线、仅 tag 表示正式发布」的 gitflow 语义不一致。本 ADR 记录修订后的 CI 工作流与镜像发布策略。

**关键词**：paths-filter、全量 test、tag-only build、workflow 命名、CD 留给 infra-cd-compose

## 涉及文件

- `.github/workflows/test.yaml` — 新 Validate 层 workflow（取代 `ci.yml`）
- `.github/workflows/build-push.yaml` — 新 Build 层 workflow（取代 `docker-build.yml`）
- `.github/utils/file-filters.yaml` — paths-filter 规则文件
- `Dockerfile`、`.dockerignore` — 保留不变
- `docs/architecture.md` §8.3 — 更新 CI/CD 分层描述
- `README.md` — 更新 workflow 名与发版流程

## 决策 1：路径筛选（paths-filter）

### 问题

`infra-ci-docker` 的 CI 在 PR/push 时无条件启动 5 路 domain matrix，即使变更仅涉及 `docs/**`、`openspec/**`、`README.md` 等非业务路径。每趟 CI 消耗约 15–20 Actions 分钟，其中 80% 在等待 MySQL/Redis service container 就绪。

### 决策

引入 `dorny/paths-filter` action，在 workflow 首步按 `.github/utils/file-filters.yaml` 筛选变更路径，输出 `code` 布尔值。`lint` 与 `test` job 仅在 `code=true` 时运行。

| filter 名 | 路径 |
|-----------|------|
| `code` | `app/**`, `tests/**`, `alembic/**`, `pyproject.toml`, `uv.lock`, `Taskfile.yml`, `Dockerfile`, `.dockerignore`, `scripts/check_no_test_cross_imports.sh`, `.github/workflows/test.yaml`, `.github/workflows/build-push.yaml`, `.github/utils/file-filters.yaml` |

**不触发**（未命中 `code`）：`docs/**`, `openspec/**`, `.cursor/**`, `README.md`, `devbox.json`, `scripts/devbox_*`。

### 理由

| 方案 | 优点 | 缺点 |
|------|------|------|
| `paths-filter`（已选） | job 级精确控制；lint/test 可共用同一 filter 输出 | 多一步 checkout + filter 开销（~10s） |
| workflow 级 `paths-ignore` | 配置简单 | 无法 job 级分别控制；一旦命中任意路径所有 job 都跑 |

### 代价

- docs-only PR 跳过 test，漏改 docs 中代码引用不报错——可接受，改代码路径会触发 test。
- filter 输出 `code=false` 时 lint/test 均 skip，但 `filter` job 本身仍需 checkout + filter 步骤。

## 决策 2：单 job 全量 test（废止 domain matrix）

### 问题

原有 5 路 matrix（user/catalog/ordering/infra/unit）并行看似快，但每个 job 都启动独立 MySQL + Redis service container，总 Actions 分钟 = 最慢一路 × 5。单体现有 ~250 用例、跨 domain service 耦合，matrix 不减少测试范围、只增加运维复杂度。

### 决策

```text
test:  单 job → mysql + redis → migrate → task test（全量，与本地 task ci 一致）
```

- 无 `strategy.matrix`，无 `setup-matrix` job
- 无 `workflow_dispatch` 的 `domain` 输入；**保留**无输入 `workflow_dispatch` 手动全量 lint + test（跳过 paths-filter）
- allure artifact 无 domain 后缀（单一 `allure-results`）；CI job 通过 workflow 层 `PYTEST_ADDOPTS` 收集，不另增 Taskfile 子命令

### 理由

| 方案 | 总 Actions 分钟 | 维护成本 |
|------|----------------|---------|
| 5 路 matrix（旧） | 5 × 最慢一路（~25–40 min） | 高：setup-matrix、case 语句、5× service 等待 |
| 单 job 全量（已选） | 1 × 全量（~5–8 min） | 低：与本地 `task ci` 一致 |

### 代价

- 全量 test 单次 wall time 略长于 matrix 单路（但总 Actions 分钟更低）。
- 单 job 失败无法区分是哪一域出的问题——本地可复现，Allure 报告内按目录查看。

## 决策 3：tag-only build（废止 main push 构建）

### 问题

原有 `docker-build.yml` 在 `push main` 和 `v*` tag 都触发构建，镜像 tag 含 `latest`、`sha-<short>`、`vX.Y.Z`、`vX.Y`、`vX` 等浮动标签。这与 gitflow 语义不一致——main 是"可演示基线"而非"自动发布"，tag 才应代表正式发布。

### 决策

```yaml
on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"
  workflow_dispatch:
    inputs:
      version:
        required: true
        description: "Semver X.Y.Z（不含 v 前缀）"
```

- **不**监听 `push: branches: main`
- 镜像 tag = 从 `GITHUB_REF_NAME` 去 `v` 前缀 → 仅 `X.Y.Z`
- **不** push `latest`、`sha-*`、`X.Y`、`X` 等浮动/衍生 tag
- job 内 semver regex 校验：`^[0-9]+\.[0-9]+\.[0-9]+$`
- 保留 `/health` 烟雾测试

### 理由

| 方案 | 触发 | 镜像 tag |
|------|------|---------|
| main push + `v*`（旧） | 每 merge main 都 build | `latest`, `sha-<short>`, semver 多级 |
| tag-only `vX.Y.Z`（已选） | 仅显式 tag | 仅 `X.Y.Z` |

gitflow 语义对齐：
- `main` = 可演示基线（仅 PR 合并），**不**自动产镜像
- `vX.Y.Z` tag = 正式发布契约，触发 build
- 发布流程：main test 绿 → `git tag vX.Y.Z` → push tag → build-push → GHCR

### 代价

- 删除 main push build 后不再有"每 merge 即镜像"——intentional，发版需打 tag。
- tag 可能打在未完全测试的 commit——流程要求先 main test 绿才打 tag。

## 决策 4：workflow 文件命名与 display name

### 决策

| 旧文件 | 新文件 | `name:` | 用途 |
|--------|--------|---------|------|
| `ci.yml` | `test.yaml` | `Run Tests` | Validate 层 |
| `docker-build.yml` | `build-push.yaml` | `Build and Push Container Images` | Build 层 |

理由：与 capstone 参考项目对齐；`gh workflow run "Run Tests"` 语义清晰。

## 决策 5：failure-alert job

### 决策

```yaml
test-failure-alert:
  needs: [filter, lint, test]
  if: always() && (failure() || cancelled())
  steps:
    - run: exit 1
```

- 上游任 job 失败或取消时，alert job 以非零退出码失败
- 全部 skip（filter 输出 `code=false`）时 alert 不跑
- 确保 GitHub branch protection `required checks` 在上游失败时正确阻塞合并

## 决策 6：CD 留给 infra-cd-compose

本 change **不**实现 CD/Deploy。后续 `infra-cd-compose` change 将处理：SSH 部署、docker-compose 生产编排、tag 后自动上线。本 change 的 build-push workflow 为 CD 预留了清晰的 semver 镜像契约——CD 只需监听 GHCR tag 事件即可。

## 不做的决策

- pre-release tag（如 `v1.0.0-rc.1`）：不支持，仅 `vX.Y.Z`
- K8s/GitOps（ArgoCD/Flux）/release-please：不引入
- PR 分域 test 筛选：单体跨域耦合，全量 test 更简单可靠
- `actions/cache` 以外的 CI 加速：暂不引入 `act` 本地运行、remote cache 等

## 迁移计划

1. feature 分支从 `dev` 切出 → 创建新 workflow + file-filters + ADR + 删旧 yml
2. `devbox run -- task ci` 本地全绿
3. push → 验证 paths-filter（docs-only vs code PR）
4. merge dev → 在 main 打 test tag → 验证 build-push + GHCR tag
5. 更新 GitHub branch protection required checks 为 `Run Tests`
6. archive change + sync specs

## 回滚

恢复旧 workflow 文件（`ci.yml`、`docker-build.yml`），删除新文件（`test.yaml`、`build-push.yaml`、`file-filters.yaml`），还原 `architecture.md` §8.3 和 `README.md`。
