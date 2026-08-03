## ADDED Requirements

### Requirement: Build-push workflow naming

Build 层 workflow 文件 SHALL 命名为 `.github/workflows/build-push.yaml`，workflow `name` SHALL 为 `Build and Push Container Images`。

#### Scenario: workflow 文件与 display name

- **WHEN** 查看 `.github/workflows/build-push.yaml`
- **THEN** 首行 `name:` SHALL 为 `Build and Push Container Images`
- **AND** 旧文件 `docker-build.yml` SHALL NOT 存在

### Requirement: Release tag semver image tag

build workflow SHALL 从 git tag `vX.Y.Z` 推导镜像 tag：去掉前缀 `v` 得到 `X.Y.Z`，并 **仅** push 该精确 tag 至 GHCR（如 `ghcr.io/<owner>/e-commerce-system:1.0.0`）。**SHALL NOT** push `latest`、`sha-*`、`X.Y`、`X` 等浮动或衍生 tag。

#### Scenario: v1.0.0 tag 映射为 1.0.0 镜像

- **WHEN** push git tag `v1.0.0` 触发 build-push workflow
- **THEN** GHCR SHALL 存在 tag 为 `1.0.0` 的镜像
- **AND** SHALL NOT 存在因该次 build 新 push 的 `latest` tag

#### Scenario: 非标准 tag 不触发 build

- **WHEN** push git tag `v1.0` 或 `v1` 或 `release-foo`
- **THEN** build-push workflow SHALL NOT 运行

#### Scenario: workflow_dispatch 手动 semver

- **WHEN** 通过 workflow_dispatch 触发且输入合法 `version=1.2.3`
- **THEN** build SHALL push 镜像 tag `1.2.3`

## MODIFIED Requirements

### Requirement: Docker build workflow trigger

GitHub Actions SHALL 提供独立 workflow（`build-push.yaml`），**仅**在 **push 匹配 `v[0-9]+.[0-9]+.[0-9]+` 的 git tag** 时自动触发。**SHALL NOT** 在 push 到 `main` 分支、feature 分支 push 或 pull_request 上默认触发镜像 build。workflow MAY 支持 `workflow_dispatch` 手动触发（须输入合法 semver `X.Y.Z`）。

#### Scenario: semver tag 触发 build

- **WHEN** push tag `v1.0.0`
- **THEN** build-push workflow SHALL 运行
- **AND** 镜像 tag SHALL 为 `1.0.0`（不含 `v` 前缀）

#### Scenario: main push 不触发 build

- **WHEN** commit push 到 `main` 且无匹配 semver tag
- **THEN** build-push workflow SHALL NOT 运行

#### Scenario: feature 分支 push 不触发

- **WHEN** 仅 push 到 `feature/*` 且无 tag push
- **THEN** build-push workflow SHALL NOT 自动运行

### Requirement: GHCR image push

build workflow SHALL 将镜像 push 至 **GHCR**（`ghcr.io/<owner>/e-commerce-system` 或文档约定等价路径）。workflow SHALL 配置 `permissions.packages: write`（或等价）以允许 push。每次成功 build 产生的可拉取 tag SHALL 与当次 release semver 一致（见 Release tag semver image tag requirement）。

#### Scenario: 构建成功后镜像可拉取

- **WHEN** build-push workflow 成功完成且 tag 为 `v2.1.0`
- **THEN** GHCR SHALL 存在 tag `2.1.0` 的镜像

## REMOVED Requirements

### Requirement: Docker build workflow trigger（main push 场景）

**Reason**: main 为可演示基线而非每次 merge 自动发布；镜像 build 绑定显式 release tag。

**Migration**: 发版时在 main 上打 `vX.Y.Z` tag 触发 build；日常 main merge 仅依赖 test workflow。
