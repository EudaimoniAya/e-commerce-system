## 1. 决策与路径筛选配置

- [ ] 1.1 新增 `docs/decision/ADR-006-CI工作流与镜像发布策略.md`（paths-filter、全量 test、tag-only build、workflow 命名；CD 留给 infra-cd-compose）
- [x] 1.2 新增 `.github/utils/file-filters.yaml`（`code` 过滤器路径与 design §2 一致）

## 2. Test workflow（TDD：先写 workflow 结构，再本地/远程验证）

- [x] 2.1 新增 `.github/workflows/test.yaml`（name: `Run Tests`）：`filter` + `lint` + 单 job 全量 `task test` + `test-failure-alert`；`dorny/paths-filter` 与 actions SHA 锁定
- [x] 2.2 删除 `.github/workflows/ci.yml`；确认无残留对 `CI` workflow name 的引用

## 3. Build-push workflow

- [x] 3.1 新增 `.github/workflows/build-push.yaml`（name: `Build and Push Container Images`）：**仅** tag `v[0-9]+.[0-9]+.[0-9]+` + `workflow_dispatch`（必填 semver）；镜像 tag = 去 `v`；job 内 semver regex 校验；保留 `/health` 烟雾
- [x] 3.2 删除 `.github/workflows/docker-build.yml`；移除 `docker/metadata-action` 多 tag 逻辑

## 4. 文档同步

- [ ] 4.1 更新 `docs/architecture.md` §8.3（test.yaml / build-push.yaml 结构；废止 matrix 与 main push build）
- [ ] 4.2 更新 `README.md`（workflow 名、`gh workflow run` 示例、发版流程：main test 绿 → `git tag vX.Y.Z` → build-push）

## 5. 本地与远程验证

- [ ] 5.1 本地：`devbox run -- task ci` 全绿
- [ ] 5.2 远程：push feature 分支；验证 code 变更 PR 触发 `Run Tests`；验证 docs-only 变更 skip test
- [ ] 5.3 远程：merge 后于 main 打测试 tag（如 patch 版本）验证 `Build and Push Container Images` 与 GHCR tag `X.Y.Z`（可选：测完删测试 tag/镜像）
- [ ] 5.4 GitHub branch protection：将 required checks 更新为 `Run Tests`（及相关 job）；记录于 tasks 或 README

## 6. 收尾

- [ ] 6.1 archive change 并 sync `openspec/specs/infra-ci`、`openspec/specs/infra-docker`
