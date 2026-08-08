## 1. 文档与分支

- [x] 1.1 从 `dev` 切分支 `style/infra-ruff-style`（**非** `feature/*`；与 ADR-008 新增 `style/*` 定义一致）
- [x] 1.2 更新 `docs/decision/ADR-008-Git分支生命周期与提交工作流规范.md`：commit type 增加 `style`；分支前缀增加 `style/*` 定义及与 `feature/*`、`docs/*` 对照；短标签示例增加 `infra-ruff-style` → `[ruff-style]`

## 2. Ruff 配置与 Taskfile

- [x] 2.1 更新 `pyproject.toml`：`extend-select` 增加 `I`、`UP`、`B006`、`B007`、`B904`（**不**整包 `B`；不启用 B008/B905，理由见 design.md）；保留 ANN 与 `app/**`、`alembic/**` per-file-ignores；isort `known-first-party` **已验证**：Ruff 默认 `src` 含项目根、`app`/`tests` 自动识别为 first-party（抽查 isort diff 分组正确），**不配**
- [x] 2.2 更新 `Taskfile.yml`：新增 `format`（`ruff format .`）、`format:check`（`ruff format --check .`）；`ci` 增加 `format:check` 于 `ruff` 之前
- [x] 2.3 更新 `.github/workflows/test.yaml` lint job：在 `task ruff` 前增加 `task format:check`
- [x] 2.4 更新 `README.md`：Task 表补充 `format` / `format:check`；`task ci` 描述含 format check；说明仓库根 `.git-blame-ignore-revs` 及 `git config blame.ignoreRevsFile .git-blame-ignore-revs`
- [x] 2.5 新增仓库根 `.git-blame-ignore-revs`（stub：注释 + 占位说明，**尚无 SHA**；格式见 design.md §4）

## 3. 全库 mechanical fix（单独 commit，type `style`）

- [x] 3.1 运行 `uv run ruff format .` 格式化全库 Python（61 reformatted / 135 unchanged）
- [x] 3.2 运行 `uv run ruff check --fix .` 修复 I/UP/B 可自动修复项（140 fixed）；剩余 7 处手工修复：B904×6（`from exc`/`from None`）+ UP046×1（PEP 695 泛型）。**UP017** 2 处已被 `--fix` 安全自动修复（`timezone.utc` → `datetime.UTC` 别名，aware 语义不变）
- [x] 3.3 确认 diff **无**业务逻辑变更（仅格式、import 顺序、UP 语法现代化、B904/UP046 机械修复）

## 4. Git blame ignore（SHA 写入文件内）

- [x] 4.1 Commit B（§3 mechanical）完成后，在 `.git-blame-ignore-revs` **内**追加该 commit 完整 SHA（保留文件头注释；附 `infra-ruff-style` 说明）
- [x] 4.2 README 已含 blame ignore 配置说明（可与 2.4 合并完成）

## 5. 本地与远程 CI 验证

- [ ] 5.1 本地：`devbox run -- task ci` 全绿（format:check + ruff + check-test-imports + test；须先 `db:up` + `redis:up`）
- [ ] 5.2 远程：push 后确认 GitHub Actions `Run Tests` lint + test 全绿（或 `workflow_dispatch` on feature branch）
- [ ] 5.3 勾选 tasks.md 全部项；准备 archive

## 6. 收尾

- [ ] 6.1 archive change 并 sync `openspec/specs/infra-ci/spec.md`、`openspec/specs/infra-toolchain/spec.md`
