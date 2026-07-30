# Gitflow：从 main 切分支导致 Graph 混乱

## 场景

采用 **gitflow 简化版**：`feature/*`、`docs/*` → `dev`（默认分支）→ 发版 PR → `main` + tag。

在 **`dev → main` 发版 PR 合并并打 tag（如 v1.0.0）之后**，未切回 `dev`，而是从 **`main` 上该发版 merge commit** 创建新分支（如 `docs/merchant-tenant`），再 PR 合入 **`dev`**。合并后 Git Graph 出现多余折线，`dev` 与 `main` 尖端不一致，与「里程碑式收束」预期不符。

本仓库真实时间线（2026-07）：

| PR | 方向 | 结果 commit | 说明 |
|----|------|-------------|------|
| #19 | dev → main | `78803c1` (v1.0.0) | 发版 merge；此时 dev 仍在 `970e83f`，main 多 1 个 merge commit |
| — | 从 **main@78803c1** 切 `docs/merchant-tenant` | `8e43170` | **错误基点** |
| #20 | docs/merchant-tenant → dev | `a080db3` | Graph 出现从 main 绕回 dev 的折线 |
| #21 | dev → main | `b550d75` | 将 ADR 等同步至 main |
| — | dev 上 `pull origin main`（back-merge） | dev → `b550d75` | 与 main 尖端对齐 |

## 问题

### 现象

1. **Graph 变乱**：`dev` 主线上出现「经 main 发版 merge 再插回」的侧枝，而非从 dev 尖端单线延伸。
2. **dev / main 尖端不一致**：发版 PR 合并后，`main` 比 `dev` **多 1 个 merge commit**（hash 不同，内容通常已等价）。
3. **误操作风险**：在 **dev** 上执行 `git pull origin main` 会把 dev **快进**到 main 的 merge commit；若未意识到，会以为「PR 自动同步了两边」。

### 典型错误 Graph 形状

```text
dev (a080db3) ── merge PR #20 ── docs/* ── 来自 main@78803c1
                                              │
main (78803c1) ── merge PR #19 ───────────────┘
```

正确形状应为：`docs/*` 从 **dev 尖端** 切出，PR 回 dev，无「绕经 main 发版点」的侧枝。

## 根因

### 1. merge commit 占一个节点（不是「内容神秘」）

`dev → main` 使用 **Create merge commit** 时，**main** 会新增 merge commit **M**，即使 **零冲突** 也会如此。  
**M 的存在是为记录「两线历史在此汇合」**（拓扑），不是因为 merge 里冲突解决「dev 不知道内容」。

发版后常见状态：

```text
dev  → A   （合 PR 前的 dev 尖端）
main → M   （M 的 parent 之一为 A）
```

**内容**往往已与 A 等价，**ref / Graph** 不同。

### 2. 从 main 切分支再合 dev

从 **main@M** 切出的分支，祖先链 **包含发版 merge 路径**；合入 **dev@A** 时，Graph 必然与「只从 dev 切 feature」不同。

### 3. Git 不会自动 back-merge

**`dev → main` 的 PR 只更新 main**，不会把 main 的 merge commit 写回 dev。  
若不在发版后 **主动 `dev merge main`**，dev 会长期停在 A，main 在 M。

### 4. feature/* 与双线增长

- **feature/docs/* 用完即扔**（合 dev 后可删远程分支），不必保留在 Graph 过滤之外。
- **dev、main 永久保留**，双线都会增长；发版只让 **main 多 merge 节点**，除非 back-merge。

## 解决

### 1. 规范流程（预防）

```text
feature/docs/* ──PR──▶ dev ──PR（发版）──▶ main + tag
                         ▲                      │
                         └── merge main ────────┘  （发版后 back-merge）
```

| 阶段 | 做法 |
|------|------|
| **签出** | **只从 dev**：`git switch dev && git pull origin dev && git switch -c feature/xxx` |
| **禁止** | 发版后从 **main** 切日常功能/文档分支（**hotfix** 除外） |
| **发版** | `dev → main` PR，在 main 打 tag |
| **发版后** | `git switch dev && git merge origin/main && git push origin dev` |
| **hotfix** | 从 **main/tag** 切 → 合 **main + dev** |

### 2. 已乱后的收口（不重写历史，推荐）

本仓库采用：

1. **PR：dev → main**（如 #21），把 dev 上独有提交同步到 main。
2. **back-merge**：在 dev 上 `git merge origin/main` 或 `git pull origin main`（常为 fast-forward），使 dev/main **尖端一致**。
3. **以后** 严格从 dev 切分支。

**不删除** 历史 feature 分支也可；Graph 用 **first-parent** 或只显示 `dev`/`main` 查看主线。

### 3. 已乱后的拉直 dev（仅 solo、可 force push）

若必须抹平 PR #20 的 merge 形状：

```bash
git switch dev
git reset --hard <PR#20 之前 dev 的 commit>   # 本例：970e83f
git cherry-pick <ADR 等功能 commit>            # 本例：8e43170
git push --force-with-lease origin dev
# 再 dev → main PR
```

协作仓库 **慎用** force push。

### 4. 发版前在错误分支上修正（PR 未合并时）

```bash
git switch docs/merchant-tenant
git rebase origin/dev
git push --force-with-lease
# 再 PR → dev
```

## 自查命令

```bash
# 各分支上游（同步更改 pull/push 的对象）
git branch -vv

# 尖端是否一致
git log -1 --oneline dev
git log -1 --oneline main

# 发版后 main 是否比 dev 多 merge commit
git rev-list --left-right --count main...dev

# 谁把 dev 拉到了 main（reflog）
git reflog dev -10

# 只看 dev 集成主线（淡化 feature 侧枝）
git log --oneline --first-parent dev -20
```

## 与 Cursor「同步更改」

- **上游（upstream）**：本地分支默认跟踪的远程分支（如 `dev` → `origin/dev`）。
- **同步更改** 通常只对 **当前分支 ↔ 其 upstream** pull/push。
- **`git pull origin main` 在 dev 上** 是 **显式从 main 拉**，等价于 back-merge 的一种；reflog 会记为 `pull origin main: Fast-forward`。
- 在 **dev** 上日常只需 `git pull origin dev`；**发版后** 才需要 merge/pull **main**。

## 相关文档

- [ADR-007：多租户扩展——设计与暂缓计划](../decision/ADR-007-多租户扩展-设计与暂缓计划.md)（docs 分支误从 main 切出的背景）
- [项目架构](../architecture.md) §9
