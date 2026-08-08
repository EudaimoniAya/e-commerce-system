## Context

- **现状**：`pyproject.toml` 配置 Ruff 默认 lint（F/E）+ `extend-select = ["ANN"]`；`app/**` 与 `alembic/**` ignore ANN。`task ruff` 仅 `ruff check .`；`task ci` = ruff + check-test-imports + test。GitHub Actions lint job 同构。
- **缺口**：未接入 `ruff format`；未启用 I/UP/B；无 `.git-blame-ignore-revs`；ADR-008 未定义 commit type `style` 与 `style/*` 分支。
- **时机**：后续 `tests/testkit` 重命名与跨域 lint 等 refactor 将产生大量 mechanical diff，需先统一格式与 import 门禁。
- **编辑器**：开发者 Cursor 使用 `ms-python.black-formatter`（bundled **Black 25.1.0**）+ `editor.formatOnSave: true`，**未**覆盖 `lineLength`（默认 **88**，与 `pyproject.toml` 一致）。此前 **无** CI format 门禁，故并非全库均为 Black 排版。

## Black vs Ruff format（propose 实测）

Ruff formatter 与 Black **兼容但并非 100% 相同**（Ruff 自称 ~99%+）。对本仓库 **196** 个 Python 文件，用 Cursor 扩展同款 Black 25.1.0 与 `ruff format --check` 对照（Linux 复验：`61 would reformat, 135 already formatted`，与 Windows 结论一致）：

| 文件数 | Black | Ruff | 含义 |
|--------|-------|------|------|
| 135 | 已格式化 | 已格式化 | 含 Cursor save 时已跑 Black 的文件 |
| 60–61 | 需重排 | 需重排 | **两工具判定一致**；多为 alembic migration、AI/脚本批量写入、未在 Cursor 中 save 过的 tests |
| 1 | 已格式化 | 需重排 | **`tests/infra/test_error_handlers.py`** — 全库唯一规则分歧 |

**唯一分歧样本**（超长 `assert`，88 列内合法排版，拆条件 vs 拆消息）：

```python
# Black：拆条件，消息留一行
assert (
    body_id == header_id
), f"body request_id ({body_id}) 应与 header ({header_id}) 一致"

# Ruff：条件留一行，消息拆行
assert body_id == header_id, (
    f"body request_id ({body_id}) 应与 header ({header_id}) 一致"
)
```

**对 infra-ruff-style 的含义**：

1. Task 3 的 format diff **不是**「推翻已有 Black 风格」——60/61 文件两工具会改出**相同**排版；风险低于「Black 与 Ruff 全面冲突」的假设。
2. 可见的风格迁移主要是上述 1 处 assert（及今后新代码统一按 Ruff 权威）。
3. **可选**：`[tool.ruff.format] quote-style = "double"`（项目已全双引号，默认即兼容；显式写出便于与 Black 文档对齐）。
4. **apply 后建议**（文档/README 一笔带过，非本 change 阻塞）：Cursor 可改 Ruff 扩展作 formatter，或继续 Black 保存 + 提交前 `task format`；**CI 权威为 Ruff**。


**Goals:**

- 本地与 CI 对 **Ruff format + 扩展 lint** 一致门禁
- 全库一次性 mechanical fix，单独 commit，写入 blame ignore
- ADR-008 补充 `style` commit type 与 `style/*` 分支定义
- 短标签 `[ruff-style]`，分支 **`style/infra-ruff-style`**

**Non-Goals:**

- mypy、pre-commit、跨域 import 脚本、testkit 重命名、app/ ANN 扩展

## Decisions

### 1. Ruff lint 规则集

**选择**：保留 Ruff 默认 **F/E**；`extend-select` 增加 **I**、**UP**、**B006/B007/B904**；继续 **ANN** 仅作用于 `tests/`（`app/**`、`alembic/**` per-file-ignores 不变）。

**B 子集**（`extend-select` 仅列具体规则，**不**整包启用 `B`）：

| 启用 | 说明 |
|------|------|
| B006 | 禁止 mutable default argument（`def f(x=[])` 类陷阱） |
| B007 | 未使用的 loop 控制变量 |
| B904 | `raise` in except 须 `from err` 或裸 raise |

**明确不启用**：

| 规则 | 理由 |
|------|------|
| **B008** | propose 实测 170 处，**全部为** FastAPI `Depends(...)`，等价于禁用标准 DI |
| **B905** | `zip(..., strict=...)` 强制；当前代码库 **无 `zip()` 调用**（实测 0 命中）。长度不一致属业务语义，**由测试保证**，lint 冗余 |

`pyproject.toml` 使用 `extend-select = [..., "B006", "B007", "B904"]`，勿 `extend-select = ["B"]` 以免误开 B008/B905 等未评估规则。

**I（isort）**：apply 时先**不**加 `known-first-party` 试跑——Ruff 默认 `src` 含项目根，`app`/`tests` 通常已识别为 first-party（M1：配置无害但可能冗余；以 `ruff check --select I` 判定为准再决定是否写入 pyproject）。

**UP**：target-version 已为 `py313`，启用 UP 统一现代类型语法。

**替代方案**：Black + isort 分离 → 拒绝，统一 Ruff 减少工具链。

### 2. Ruff format

**选择**：

- `task format` → `uv run ruff format .`
- `task format:check` → `uv run ruff format --check .`
- CI lint job 增加 `task format:check`（在 `task ruff` 之前或之后均可，建议 format check 先于 lint check）
- `task ci` 增加 `format:check`（与 CI 对齐）

**替代方案**：format 只本地、不进 CI → 拒绝，无法防止 drift。

**Black 迁移**：见上文「Black vs Ruff format」实测；全库一次性 `ruff format` 可接受。可选在 `pyproject.toml` 增加：

```toml
[tool.ruff.format]
quote-style = "double"
```

### 3. Task 命名

**选择**：

| Task | 命令 |
|------|------|
| `ruff` | `ruff check .`（不变） |
| `format` | `ruff format .` |
| `format:check` | `ruff format --check .` |
| `ci` | `format:check` + `ruff` + `check-test-imports` + `test` |

README Task 表同步。

### 4. 机械变更与 Git blame

**`.git-blame-ignore-revs` 放在仓库根目录**（与 `pyproject.toml` 同级），**纳入版本库**；GitHub Web Blame 对默认分支上的该文件自动生效。被忽略的 revision **写在文件里面**（一行一个完整 SHA），**不**写在 design/README 正文里替代。

**文件初始内容**（Commit A 即入库，仅注释占位）：

```gitignore
# git blame 忽略纯机械提交（无业务逻辑变更）
# 本地启用：git config blame.ignoreRevsFile .git-blame-ignore-revs
#
# infra-ruff-style: 全库 ruff format + I/UP/B006/B007/B904 lint fix
# <SHA 在 Commit B 完成后填入下方>
```

**提交顺序**：

1. **Commit A**（`ci` + 可含 `docs`）：pyproject、Taskfile、workflow、ADR、README、stub `.git-blame-ignore-revs`——**ci 与 docs 同 commit 可接受**（C3），不必强行拆分
2. **Commit B**（`style`）：`ruff format .` + `ruff check --fix .` 全库；**无**手工逻辑变更
3. **Commit C**（`chore`）：在 `.git-blame-ignore-revs` **内**追加 Commit B 的完整 SHA（可 squash 到 B 之后立刻 follow-up，勿拖延）

若仅一个 mechanical commit，该 commit 的 SHA 即唯一需写入的行。

**替代方案**：不 ignore / 仅 README 记 SHA → 拒绝，blame 将被 format commit 覆盖；SHA 只写在文档里无法被 `git blame` 读取。

### 5. 分支与 commit 规范（ADR-008）

**选择**：

- **分支**：**`style/infra-ruff-style`**（主推荐；本 change 定义 `style/*`，用自身践行）。OpenSpec 惯用 `feature/*` 仍适用于业务能力切片；**纯工具链/format/lint** 用 `style/*`
- **commit type `style`**：仅格式、import 排序、UP 语法替换、Ruff `--fix` 机械修复，**不改变运行时行为**
- **commit type `ci`**：Taskfile / workflow / pyproject 规则配置变更
- **`style/*` 分支前缀**：仅工具链/format/lint 门禁，**无** `app/` 业务行为变更；**可**改 CI/workflow（与 `docs/*` 区分）

ADR-008 决策 6 type 列表增加 `style`；决策 1 或新小节增加 `style/*` 与 `feature/*`、`docs/*` 对照表。

### 6. Spec 变更范围

**选择**（C2 拍板：**方案 B**）：

| Capability | 内容 |
|------------|------|
| **`infra-toolchain`**（新建） | pyproject Ruff 规则、Taskfile `format`/`format:check`、`.git-blame-ignore-revs` |
| **`infra-ci`**（修改） | lint job / `task ci` 增加 `format:check` |

Git blame 与「CI/CD Validate 层」语义不符，**不**挂在 `infra-ci` ADDED 下。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 全库 format PR diff 巨大 | 单独 `style` commit + blame ignore；与功能变更 PR 分离；多数为从未 Black 格式化的文件 |
| B008 与 FastAPI `Depends()` 冲突 | 不纳入 extend-select；已实测 170 处全为 Depends |
| B905 与测试职责重叠 | 不启用；当前无 zip()，业务长度校验由 pytest 覆盖 |
| UP 改类型语法导致 review 噪音 | 与 format 同一 mechanical commit |
| UP017 别名替换 | 实测 2 处均为 `timezone.utc` → `datetime.UTC`，aware 语义不变，可 `--fix`；若出现 `utcnow()` 等 unsafe fix 须人工审查 |
| 开发者本地未 format 导致 CI 红 | README 文档 `task format`；CI `format:check` 报错清晰 |
| blame ignore SHA 遗漏 | tasks.md 明确 Task 顺序与 follow-up commit |
| lint job 无 uv cache（R2） | **范围外**；后续 infra-ci change 可给 lint job 加 `actions/cache` |

## Migration Plan

1. 从 `dev` 切 `style/infra-ruff-style`
2. apply Task 1–3：配置 + 全库 fix + blame ignore
3. `devbox run -- task ci` 本地全绿
4. merge dev → 远程 CI 全绿 → archive

**Rollback**：revert mechanical commit + 配置 commit；移除 pyproject 新规则与 CI format step。

## Open Questions

（无——B008/B905 已在 propose 阶段结论为不启用。）
