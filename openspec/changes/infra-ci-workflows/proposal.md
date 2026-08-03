## Why

`infra-ci-docker` 交付的 CI 使用 5 路 domain matrix 并行 pytest，且 PR/push 无路径筛选——文档、openspec 等变更仍会触发完整 lint + test；Build workflow 在 `main` push 与 `v*` tag 双触发，镜像 tag 含 `latest`/`sha-*` 等浮动标签，与「main 为可演示基线、仅 tag 表示正式发布」的 gitflow 语义不一致。现需在 `infra-cd-compose`（Deploy）之前，修订 Validate + Build 层 workflow 设计，降低 Actions 消耗、对齐 capstone 式命名（`test` / `build-push`），并为后续 tag 触发全自动 CD 预留清晰的 semver 镜像契约。

## What Changes

- **Test workflow 重命名与简化**：`.github/workflows/ci.yml` → `test.yaml`（name: `Run Tests`）；去掉 domain matrix 与 `workflow_dispatch` 的 `domain` 输入；单 job 全量 `task test`；**保留**无输入 `workflow_dispatch` 手动全量 test
- **路径筛选**：引入 `dorny/paths-filter` + `.github/utils/file-filters.yaml`；仅业务代码变更时跑 lint + test；docs/openspec 等可跳过
- **failure-alert job**：参考 capstone，避免 branch protection 在 skip 时误判（上游失败仍 fail）
- **Build workflow 重命名与触发修订**：`.github/workflows/docker-build.yml` → `build-push.yaml`（name: `Build and Push Container Images`）；**仅** push 匹配 `vX.Y.Z` 的 git tag 触发（标准 release，不含 pre-release）；**移除** `main` push 触发
- **镜像版本号**：从 `GITHUB_REF_NAME` 去掉前缀 `v` 作为唯一镜像 tag（如 `v1.0.0` → `1.0.0`）；**不** push `latest`、`sha-*`、`1.0`、`1` 等浮动 tag
- **workflow_dispatch**：build-push 可选手动触发，须输入合法 semver（`X.Y.Z`）
- **ADR-006**：记录 CI workflow 与 tag-only release build 决策（编号 006，填补 ADR 序列空缺）
- **文档与 spec 同步**：更新 `docs/architecture.md` §8.3、README；修订 `infra-ci`、`infra-docker` 主 spec（**BREAKING**：废止 domain matrix、main push build 等旧要求）

## Non-goals

- **不** 实现 CD / Deploy（SSH、docker-compose 生产编排、tag 后自动上线）—— 留给后续 `infra-cd-compose`
- **不** 引入 K8s、GitOps（ArgoCD/Flux）、release-please 自动发版
- **不** 做 PR 上的 domain 分域 test 筛选（单体跨域耦合，全量 test 更简单可靠）
- **不** 支持 pre-release tag（如 `v1.0.0-rc.1`）、`vX`/`vX.Y` 等非标准 tag 构建镜像
- **不** 修改业务域代码（user / catalog / ordering）；本 change 仅影响 **infra** 工程层

## Capabilities

### New Capabilities

（无——本 change 修订现有 infra-ci / infra-docker 能力，不新增 capability 目录。）

### Modified Capabilities

- `infra-ci`：废止 domain matrix 与 workflow_dispatch `domain` 筛选；新增 paths-filter、单 job 全量 `task test`、无输入 `workflow_dispatch`、workflow 重命名 `test.yaml`、failure-alert
- `infra-docker`：废止 main push 触发与浮动镜像 tag；改为 tag-only `vX.Y.Z` 触发、镜像 tag = 去 `v` 的 semver；workflow 重命名 `build-push.yaml`

## Impact

- **影响域**：infra（CI/CD Validate + Build 层）
- **新增/修改文件**：
  - `.github/workflows/test.yaml`、`.github/workflows/build-push.yaml`（新）
  - `.github/utils/file-filters.yaml`（新）
  - `docs/decision/ADR-006-CI工作流与镜像发布策略.md`（新）
  - 删除 `.github/workflows/ci.yml`、`.github/workflows/docker-build.yml`
  - `docs/architecture.md`、`README.md`
  - `openspec/specs/infra-ci/spec.md`、`openspec/specs/infra-docker/spec.md`（archive/sync 时合并 delta）
- **保留不变**：`Dockerfile`、`.dockerignore`；Allure artifact 改为单 job 上传
- **Taskfile 精简**：删除 `test:user` 等分域子命令；本地与 CI 统一 `task test` / `task ci`
- **运维**：GitHub branch protection 需将 required checks 从旧 workflow/job 名更新为 `Run Tests` 等新名称（tasks 中记人工步骤）
