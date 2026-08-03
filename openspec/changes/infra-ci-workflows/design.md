## Context

`infra-ci-docker`（已 archive）交付了 `.github/workflows/ci.yml`（lint + 5 路 domain matrix test）与 `docker-build.yml`（main push + `v*` tag → GHCR，metadata-action 生成 `latest`/semver/`sha-*`）。当前问题：

1. **无路径筛选**：docs、openspec、devbox 等变更仍触发完整 lint + 5×（mysql + redis + migrate + pytest）
2. **domain matrix 收益有限**：单体 ~250 用例、跨域 service 耦合；matrix 增加 Actions 分钟而非减少测试范围
3. **Build 触发与 gitflow 语义不一致**：main 每次 merge 产镜像；浮动 tag 不利于「tag = 正式发布」
4. **workflow 命名**：与 capstone 参考项目不一致（`test` / `build-push`）

约束：

- GitHub Actions `uses:` 须锁定 commit SHA（`.cursor/rules/github-actions-pinning.mdc`）
- 本地 MySQL/Redis 仍 devbox（ADR-002）；CI 仍 `services.mysql` + `services.redis`
- Deploy（CD）留给 `infra-cd-compose`；本 change 不链接 deploy workflow

## Goals / Non-Goals

**Goals:**

- `test.yaml`（name: `Run Tests`）：paths-filter + lint + 单 job 全量 `task test` + `workflow_dispatch`（无输入）+ failure-alert + uv cache
- `build-push.yaml`（name: `Build and Push Container Images`）：**仅** `vX.Y.Z` tag 触发；镜像 tag = `${GITHUB_REF_NAME#v}`；`/health` 烟雾
- `.github/utils/file-filters.yaml`：业务代码 vs 可跳过路径
- `docs/decision/ADR-006-CI工作流与镜像发布策略.md` 记录决策
- 修订 `infra-ci`、`infra-docker` delta spec；更新 architecture §8.3、README

**Non-Goals:**

- CD / deploy / tag 后自动上线（`infra-cd-compose`）
- pre-release tag、main push build、`latest`/`sha-*` 浮动镜像 tag
- PR 分域 test 筛选
- 修改 Taskfile：删除 `test:user` 等分域子命令；本地与 CI 统一 `task test` / `task ci`

## Decisions

### 1. Test：单 job 全量 pytest（非 domain matrix）

**选择**：

```text
jobs:
  filter:     dorny/paths-filter → output code=true/false；workflow_dispatch 强制 code=true
  lint:       if code → ruff + check-test-imports
  test:       if code → mysql+redis → migrate → task test（全量）
  test-failure-alert: 上游 failure/cancelled 时 fail
```

**workflow_dispatch**：无输入；手动在选定 ref 上跑全量 lint + test（跳过 paths-filter，替代旧版 `domain` 域筛选）。

**理由**：与本地 `task ci` / `task test` 一致；跨域耦合下全量更可靠；单套 service 比 5 路 matrix 省 Actions 分钟。

**备选**：保留 matrix 并行 — 否决（维护成本高、总分钟更高）。

### 2. paths-filter 规则

**选择**（`.github/utils/file-filters.yaml`）：

| filter 名 | 路径（示例） |
|-----------|-------------|
| `code` | `app/**`, `tests/**`, `alembic/**`, `pyproject.toml`, `uv.lock`, `Taskfile.yml`, `Dockerfile`, `.dockerignore`, `scripts/check_no_test_cross_imports.sh`, `.github/workflows/test.yaml`, `.github/workflows/build-push.yaml`, `.github/utils/file-filters.yaml` |

**不触发 test**（未命中 `code`）：`docs/**`, `openspec/**`, `.cursor/**`, `README.md`, 纯 `devbox.json` / `scripts/devbox_*`（除非后续扩展 `lint-only` filter）。

**理由**：capstone 同款 `dorny/paths-filter`；docs-only PR 跳过 test。

**备选**：workflow 级 `paths-ignore` — 否决（无法 job 级 lint/test 分离）。

### 3. failure-alert job

**选择**：参考 capstone `run-tests-failure-alert`：`needs: [filter, lint, test]`，`if: cancelled() || failure`，`exit 1`。

**理由**：上游 job 失败时 required check 仍 fail；filter 跳过 test 时 alert 不跑（无 failure）。

### 4. Build：tag-only `vX.Y.Z`

**选择**：

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
- job 内：`VERSION="${GITHUB_REF_NAME#v}"`（tag 触发）或 `inputs.version`（dispatch）
- regex 校验：`^[0-9]+\.[0-9]+\.[0-9]+$`
- 镜像 tag：**仅** `ghcr.io/<owner>/repo:${VERSION}`（不用 metadata-action 多 tag）

**理由**：tag = 发布契约；main = 可演示基线但不自动产镜像；版本号唯一可追溯。

**备选**：
- main push + extended version（capstone staging）— 否决（与 gitflow 发版语义冲突）
- `v*` 宽泛 pattern — 否决（会匹配 `v1`、`v1.0`）

### 5. workflow 文件与 display name

| 旧 | 新 | `name:` |
|----|-----|---------|
| `ci.yml` | `test.yaml` | `Run Tests` |
| `docker-build.yml` | `build-push.yaml` | `Build and Push Container Images` |

**理由**：与 capstone 对齐；CLI `gh workflow run "Run Tests"` 可读。

### 6. Allure artifact

**选择**：单 test job 上传 `allure-results`（无域后缀）；保留 14 天。

**理由**：无 matrix 后无需按域拆分 artifact。

### 7. ADR-006

**选择**：`docs/decision/ADR-006-CI工作流与镜像发布策略.md`，编号 006（填补 001–005 与 007 之间空缺）。

内容：Test 路径筛选 + 全量 test；Build tag-only；main/tag/gitflow 分工；CD 留给 `infra-cd-compose`。

### 8. 保留 lint job 分离与 ripgrep

**选择**：保留独立 `lint` job（无 services）；仍 `apt install ripgrep`；lint 与 test 可并行（test `needs: filter` 即可，不 `needs: lint`）。

**理由**：延续 `infra-ci-docker` 已验证结构；lint 失败由 workflow 汇总 fail。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| docs-only PR skip test，漏改 docs 中错误代码引用 | 可接受；改代码路径会触发 test |
| 单 job test wall time 略长于 matrix 最慢一路 | ~250 用例可接受；总 Actions 分钟更低 |
| branch protection 仍指向旧 check 名 | tasks 人工更新 GitHub UI |
| 删 main push build 后无「每 merge 镜像」 |  intentional；发版打 tag |
| tag 打在未测 commit | 流程：先 main test 绿，再打 tag |
| workflow 改名后 `gh workflow run CI` 404 | 更新 README |

## Migration Plan

1. `feature/infra-ci-workflows` 从 `dev` 切出
2. apply：新 workflow + file-filters + ADR-006 + 删旧 yml + 文档
3. `devbox run -- task ci` 本地全绿
4. push → 验证 paths-filter（docs-only vs code PR）
5. merge dev → 在 main 打 `vX.Y.Z` → 验证 build-push + GHCR tag
6. 更新 branch protection required checks
7. archive change + sync specs
8. 回滚：恢复旧 workflow 文件

## Open Questions

- （已关闭）pre-release tag — **不支持**，仅 `vX.Y.Z`
- （已关闭）main push build — **移除**
- branch protection 具体 check 名称 — apply 时在 GitHub UI 确认 `Run Tests` job 名
