# ADR-008：Git 分支生命周期与提交工作流规范

- **状态**：已采纳
- **日期**：2026-07-31
- **背景**：项目采用 gitflow 简化版（`feature/*`、`docs/*` → `dev` → 发版 PR → `main` + tag）。在 `infra-ci-workflows` 等**长线 change**（实现合入后仍需在默认分支/远程验证才能归档）出现之前，单分支单 PR 的简单模型可以覆盖所有场景。随着多 change 并行（一个 change 等待验证、其他 change 持续推进）成为常态，git 分支操作开始暴露教科书 gitflow 未覆盖的边界：**部分合并过的分支能否 rebase？长线 change 的 branch 何时删除？哪些提交可以直接上 dev？** 本 ADR 固化从真实踩坑（`gitflow-从main切分支导致Graph混乱.md`）与多 change 并行实践中总结出的分支生命周期与提交规范。

**关键词**：gitflow、change 生命周期、多段 merge、back-merge、rebase 边界、直接提交 dev、长线验证

## 涉及文件

- `docs/troubleshooting/gitflow-从main切分支导致Graph混乱.md` — 踩坑记录（本 ADR 的根因来源）
- `docs/architecture.md` §9 — 项目架构中的分支/发布流程
- `openspec/changes/` — change 生命周期（提案 → 实现 → 验证 → 归档）
- `CLAUDE.md` — 工作流约束（gitflow、分支前缀）

## 决策 1：分支切换基点——只从 dev 切

### 问题

`dev → main` 发版 PR 合并后，`main` 比 `dev` **多 1 个 merge commit**（零冲突也如此，merge commit 是拓扑节点而非内容变更）。此时若从 `main@merge-commit` 直接切日常分支，分支祖先链包含发版 merge 路径；合回 `dev` 时 Graph 出现"绕经 main 发版点再插回 dev"的折线，且 `dev`/`main` 尖端不一致（真实案例：`docs/merchant-tenant` 分支误从 `main@78803c1` 切出）。

### 决策

| 场景 | 做法 |
|------|------|
| **日常功能/文档分支** | **只从 `dev` 切**：`git switch dev && git pull origin dev && git switch -c feature/xxx` |
| **hotfix** | 从 `main`/tag 切 → 合 `main` + `dev`。**hotfix 合并到 main 后，dev 必须 `git pull origin main`（back-merge）**；后续日常开发**仍然只从 dev 切**，绝不因 hotfix 的存在而把 main 当作日常基点 |
| **发版后** | `git switch dev && git merge origin/main && git push origin dev`（back-merge，见决策 4） |

**关键约束**：`hotfix` 是"从 main 切分支"的**唯一例外**，且该例外**不传递**——hotfix 合入 main 只意味着 main 有了新内容，**日常开发基点永远是 dev**。保证 dev 最新（发版/hotfix 后 back-merge）是"只从 dev 切"成立的前提。

### 理由

merge commit 的本质是"两线历史在此汇合"的拓扑记录。从 main 切分支本身不产生冲突，但会把"经过发版 merge"的路径带入新分支的祖先链，污染 dev 主线的线性演进。规避方式不是修复，而是**流程上禁止**。

### 代价

- 发版后必须记得 back-merge，否则 dev 长期停在旧点、main 在前——用 `git log -1 dev` / `git log -1 main` 自查。
- 已乱后的图不重写历史（见 `gitflow-从main切分支导致Graph混乱.md` 的"已乱后的收口"），用 first-parent 查看主线。

## 决策 2：分支生命周期 = change 生命周期（非 PR 生命周期）

### 问题

教科书 gitflow 假设"分支 = 一次 PR = 一次 merge = 删除"。但 `infra-ci-workflows` 类 change 的验证**必须合入 dev 后才能生效**（workflow 文件只在默认分支可被 `workflow_dispatch`/远程验证触发），验证完成前不能归档。此时若按"合并即删"，change 的后续段（验证勾选、归档同步）将无处安放。

### 决策

```text
一个 OpenSpec change = 一条分支脉络：
  propose → 实现 merge 到 dev（分支保留） → 远程验证（可能跨越多个 dev 功能切片）
  → 验证完成 → 归档（最后一段 merge 到 dev） → 分支可删
```

- **分支在首次 merge 后不删**，仍代表该 change 的"后续段"，直到归档完成。
- 允许一个 change **多次 merge 到 dev**（实现一次、归档一次，中间可能有 fix）。
- 长线 change 挂起期间，**最多允许 1–2 个新功能切片插队**（时间/数量约束，防止老 change 被无限期拖死）。
- 新功能切片从 `dev` 最新尖端切出，正常单 PR 闭环，不等待长线 change。

### 理由

验证长线 change 依赖"真实发版/默认分支行为"，而非构造测试提交。挂起期间推进其他 change 是正常的流水线并行；分支保留使 change 的完整生命周期（从 propose 到归档）在同一条线上可追溯。

### 代价

- 多条长线并存时 git 图出现"从底部上升"的侧枝——**接受**，这是真实工作流的拓扑，不强行 rebase 抹平（见决策 3）。
- 需要人工判断"该 change 是否已超期"——solo 场景由开发者自审；协作场景由排程/提醒机制覆盖。

## 决策 3：rebase 与 merge 的适用边界

### 问题

长线分支等待验证期间，dev 前进 N 个 commit。合回 dev 前是否 rebase？直接 rebase 会触发大量冲突，且部分合并过的分支 rebase 后 merge commit 丢失、提交身份（SHA）被改写。

### 决策

**按分支是否"部分合并过"区分：**

| 分支状态 | 同步方式 | 原因 |
|----------|---------|------|
| **干净分支**（从未 merge 到 dev，仅本地开发） | `git rebase dev` 后合并 | 提交内容为全新增量，rebase 无冲突；"好像自己就是从 dev 最新处开发" |
| **脏分支**（已部分 merge 到 dev，如长线 change） | **不 rebase**，直接 `git merge --no-ff` | 已合入的提交内容在 dev 中已存在，rebase 必然冲突；merge 保留真实拓扑 |

**rebase 的语义说明：**

- rebase 不是丢弃提交，而是在新基点**重新生成**提交（内容等价、SHA 改变）。
- rebase **默认丢弃 merge commit**（`M` 的父节点在新基点上不存在，无法重建）。已部分合并过的分支 rebase 后，此前"合并过"的拓扑信息会丢失。
- rebase 后旧提交仍存在于 reflog（约 90 天），但不再出现在图上。

### 理由

rebase 的收益（图整洁）只在"分支未与 dev 共享历史"时成立；一旦共享（部分合并），rebase 的冲突成本超过图形美观收益。**真实拓扑优先于视觉整洁**——merge 产生的侧枝是工作流的事实记录。

### 代价

- 脏分支合入后图中出现从旧基点拉到顶部的侧枝——已接受（决策 2 代价）。
- rebase 后需要 `--force-with-lease` 推送（干净分支场景）——solo 无协作冲突，但养成习惯。

## 决策 4：back-merge（发版后 dev 同步 main）

### 问题

`dev → main` 的 PR 只更新 main，**不会**把 main 的 merge commit 写回 dev。不主动 back-merge 则 dev/main 尖端长期不一致，且容易在 dev 上误执行 `git pull origin main` 造成意外的 fast-forward。

### 决策

```text
feature/docs/* ──PR──▶ dev ──PR（发版）──▶ main + tag
                         ▲                      │
                         └── merge main ────────┘  （发版后 back-merge）
```

- **发版后**：`git switch dev && git merge origin/main && git push origin dev`。
- 平时 dev 只 `git pull origin dev`（日常同步对象是 dev 自己，不是 main）。
- 自查：`git log -1 --oneline dev` 与 `git log -1 --oneline main` 尖端是否一致；`git rev-list --left-right --count main...dev` 判断差异方向。

### 理由

dev/main 双线永久增长；back-merge 是让两条永久分支尖端收敛的唯一手段，也是后续分支从 dev 切时基点正确的前提。

### 代价

- 每次发版多一步操作——由发版检查单覆盖，防止遗漏。

## 决策 5：直接提交 dev 的边界

### 问题

严格 gitflow 要求一切变更走分支 + PR。但 docs 调整、极小 bug 修复走完整分支流程成本远高于收益，且 dev 上"无 PR 提交"在 solo 场景无协作风险。

### 决策

满足**全部**条件时允许直接 commit 到 dev：

1. **无行为变更**（docs、ADR、troubleshooting、openspec 提案）或**极小行为变更**（typo、常量修正、单行修复）。
2. 当前 dev 无等待验证的 change 依赖该提交（避免混入长线验证的审查范围）。
3. commit message 写清变更原因（commit message 本身即说明，见决策 6）。

违反任意一条 → 走分支 + PR。**API 契约、schema、数据库结构、workflow 行为变更一律禁止直接提交。**

### 理由

纪律集中在发布路径（dev → main），开发路径允许灵活度；"直接提交"的成本由清晰的边界条件和 commit message 承担。

### 代价

- 直接提交进入 dev 历史后不可独立回滚（需 revert）——小变更可接受。
- 与长线 change 并行时需注意时间边界——条件 2 明确要求。

## 决策 6：commit message 规范

### 决策

沿用 Conventional Commits 风格，OpenSpec 相关提交在标题中增加 **短 change 标签**：

```text
<type>(<scope>) [<short-change>]: Task <N> <简短主题>

- <要点 1：改了什么、为什么>
- <要点 2>
```

**示例：**

```text
test(engagement) [browse]: Task 1 TDD 红

- helper: record/list/delete_browse + Browse*Result
- tests/engagement/test_browse_*.py；tests/support/db/engagement.py
```

```text
feat(ordering) [buyer-cart]: Task 4 购物车 CRUD

- catalog: PurchasableProduct 新增 shop_name 字段
- ordering/cart_service.py: CartService（批量查询避免 N+1）
```

**要求：**

- `type` 用 `feat`/`fix`/`refactor`/`docs`/`test`/`ci`/`chore`/`build`。
- `scope` 用**业务域或模块**（`ordering`、`engagement`、`infra`、`openspec` 等），**不是** OpenSpec change 全名；跨域时写 `(catalog, engagement)`。
- `[<short-change>]`：OpenSpec change 的**短标签**，便于 `git log --grep '\[browse\]'` 串联同一垂直切片。推导规则见下。
- **标题行宜短**（建议 ≤72 字符）：只写 `Task N` + 一句摘要；**不要**在标题堆「——」和长说明。
- 空一行后用 `-` 要点列表展开**变更内容 + 决策理由**（不是流水账，每个要点回答「改了什么、为什么」）。
- 关键决策在 message 中保留理由（如「commit=False 仅 flush 由 CartService 统一提交」），供半年后回顾。

**短 change 标签推导（`<short-change>`）：**

| OpenSpec change 名 | scope | `[short-change]` |
|------------------|-------|------------------|
| `engagement-browse` | `engagement` | `[browse]` |
| `engagement-favorites` | `engagement` | `[favorites]` |
| `ordering-buyer-cart` | `ordering` | `[buyer-cart]` |
| `infra-ci-workflows` | `infra` | `[ci-workflows]` |

- 默认：change 名为 `{scope}-{capability}` 时，标签取 **去掉首个 `{scope}-` 前缀** 的剩余部分。
- 若 change 名不以 scope 开头，取 change 名去掉常见前缀后的** distinctive 后缀**，或整段短名（如 `[infra-redis]` → `[redis]`）；**避免**与其它 change 标签撞名。
- propose / archive / apply 提交**均**带同一 `[short-change]`，与 `openspec/changes/<change-name>/` 对应。

### 理由

commit message 是变更的**决策记录**而非操作日志。写清楚理由的 message 使 `git log` 成为可检索的决策历史——与 OpenSpec 的 design.md 互补（design 记录"为什么这么设计"，message 记录"这次提交实现了什么"）。

## 决策 7：长线 change 的冲突解决原则

### 问题

长线 change 分支 `git pull origin dev` 后，workflow/Taskfile 等文件可能已在新功能切片中被更新，产生冲突。

### 决策

**代码以 dev 为准，openspec 记录以 feature 为准：**

- 冲突的**代码文件**（`.github/workflows/*.yaml`、`Taskfile.yml`、`app/**`）：保留 dev 版本——dev 版本已随新功能通过 CI，是最新事实。
- 冲突的 **openspec 记录**（`openspec/changes/<change>/*.md`）：保留 feature 版本——change 处于"待定 delta"状态，主 spec 才是唯一事实源，change 文档只需在归档时与最新代码一致。
- 归档时：用最新代码 + 本 change 最新规范一次性同步进主 spec。

### 理由

OpenSpec 模型中 change 是**待定的 delta**，不需要在等待期间与 dev 现状保持同步；它只需要在自己归档的那一刻成立。因此长线等待期间的文档维护成本为零，归档时做一次合并即可。

### 代价

- 归档瞬间需要完整核对 spec 与代码一致性——由 archive 流程的 DoD 检查覆盖。

## 不做的决策

- **squash merge**：会丢失 change 内的提交粒度，与"分支 = change 完整脉络"模型冲突。
- **从 main 切日常分支**：仅 hotfix 允许，且 hotfix 合入后日常基点仍为 dev（决策 1）。
- **长线 change 的强制到期自动归档**：Git/GitHub 无此机制；用 1–2 切片插队约束 + 人工门禁。
- **rebase 已发布分支**：脏分支场景明确禁止（决策 3）。
- **删除已合并历史分支**：保留作为 change 脉络的物理痕迹（远程分支可删，本地保留成本为零）。

