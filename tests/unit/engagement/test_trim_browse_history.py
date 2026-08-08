"""``plan_browse_trim_deletes`` 纯函数单元测试（TDD 红阶段）。

对齐 spec（engagement-browse "Browse trim job"）的算法契约：
- 对每个 user_id 按 ``last_viewed_at DESC`` 取 top ``max_per_user`` 保留；
- 其余行中 ``last_viewed_at < retention_cutoff`` 删除；
- top N 内行即使超 retention 也保留，直至被挤出 top N。

不触碰数据库——纯函数在内存行集上判定。使用 ``.env.test`` 小 MAX 验证配置驱动。
"""

from datetime import UTC, datetime, timedelta

import allure

from app.engagement.jobs.trim_browse_history import (
    BrowseTrimRow,
    plan_browse_trim_deletes,
)
from app.infra.config import get_settings

_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
_RETENTION_CUTOFF = _NOW - timedelta(days=30)


def _row(uid: str, last_viewed_at: datetime, row_id: str) -> BrowseTrimRow:
    """构造 trim 输入行（固定 id，便于断言集合）。"""
    return BrowseTrimRow(id=row_id, user_id=uid, last_viewed_at=last_viewed_at)


@allure.epic("engagement")
@allure.feature("trim_browse_history")
@allure.title("top N 内行即使超 retention 也保留。")
def test_trim_keeps_rows_within_top_n_even_if_old() -> None:
    """行数不超 MAX 时，最旧行（超 retention）不被删除。"""
    rows = [
        _row("A", _NOW - timedelta(days=40), "old"),  # 超 retention
        _row("A", _NOW - timedelta(days=1), "mid"),  # retention 内
        _row("A", _NOW, "new"),  # 最近
    ]

    to_delete = plan_browse_trim_deletes(
        rows,
        max_per_user=3,
        retention_cutoff=_RETENTION_CUTOFF,
    )

    assert to_delete == set()  # 全部在 top 3 内，即使 old 超 retention 也保留


@allure.epic("engagement")
@allure.feature("trim_browse_history")
@allure.title("top N 外且超 retention 的行被删除，剩余行数 ≤ MAX。")
def test_trim_deletes_rows_outside_top_n_older_than_retention() -> None:
    """超过 top N 且 last_viewed_at 早于 retention cutoff 的行被删除。"""
    # 插入顺序最旧在前：若实现按插入顺序而非 last_viewed_at DESC 选 top N，本测试会失败。
    rows = [
        _row("A", _NOW - timedelta(days=40), "r-old-1"),  # 超 retention
        _row("A", _NOW - timedelta(days=35), "r-old-2"),  # 超 retention
        _row("A", _NOW - timedelta(hours=2), "r-mid"),  # retention 内
        _row("A", _NOW - timedelta(hours=1), "r-new-1"),  # retention 内
        _row("A", _NOW, "r-new-2"),  # retention 内
    ]

    to_delete = plan_browse_trim_deletes(
        rows,
        max_per_user=3,
        retention_cutoff=_RETENTION_CUTOFF,
    )

    assert to_delete == {"r-old-1", "r-old-2"}
    remaining = len(rows) - len(to_delete)
    assert remaining == 3  # 不超过 max_per_user


@allure.epic("engagement")
@allure.feature("trim_browse_history")
@allure.title("top N 外但 retention 内的行保留（仅超 retention 才删）。")
def test_trim_keeps_rows_outside_top_n_but_recent() -> None:
    """超出 top N 但 last_viewed_at 仍 ≥ retention cutoff 的行不删除。"""
    rows = [
        _row(
            "A", _NOW - timedelta(hours=3), "beyond-top-n"
        ),  # 第 4 行，但 retention 内
        _row("A", _NOW - timedelta(hours=2), "r3"),
        _row("A", _NOW - timedelta(hours=1), "r2"),
        _row("A", _NOW, "r1"),
    ]

    to_delete = plan_browse_trim_deletes(
        rows,
        max_per_user=3,
        retention_cutoff=_RETENTION_CUTOFF,
    )

    assert to_delete == set()  # beyond-top-n 虽不在 top 3，但未超 retention → 保留


@allure.epic("engagement")
@allure.feature("trim_browse_history")
@allure.title("trim 按 user_id 独立分组。")
def test_trim_groups_by_user_independently() -> None:
    """不同用户互不影响：仅 user A 的超额超期行被删，user B 不超 N 则全保留。"""
    rows = [
        # user A：5 行，2 行超 top 3 且超 retention
        _row("A", _NOW - timedelta(days=40), "a-old-1"),
        _row("A", _NOW - timedelta(days=35), "a-old-2"),
        _row("A", _NOW - timedelta(hours=2), "a-r3"),
        _row("A", _NOW - timedelta(hours=1), "a-r2"),
        _row("A", _NOW, "a-r1"),
        # user B：2 行（均在 top 2 内）
        _row("B", _NOW - timedelta(days=40), "b-old"),  # 虽超期但仍在 top 2 内
        _row("B", _NOW, "b-new"),
    ]

    to_delete = plan_browse_trim_deletes(
        rows,
        max_per_user=3,
        retention_cutoff=_RETENTION_CUTOFF,
    )

    assert to_delete == {"a-old-1", "a-old-2"}
    assert "b-old" not in to_delete  # user B 行数未超 top 2，超期也保留


@allure.epic("engagement")
@allure.feature("trim_browse_history")
@allure.title("trim 使用 .env.test 小 MAX_PER_USER（非硬编码 50）。")
def test_trim_applies_small_config_max_per_user() -> None:
    """配置驱动的 top N：.env.test 中 MAX_PER_USER 为小值，算法按该值裁。"""
    max_per_user = get_settings().browse_history_max_per_user

    assert 0 < max_per_user <= 5  # .env.test 小 MAX，杜绝硬编码 50

    # 用配置值构造：MAX 行最近 + 1 行超 retention 超 MAX
    recent = [
        _row("A", _NOW - timedelta(hours=1), f"recent-{i}") for i in range(max_per_user)
    ]
    stale_extra = _row("A", _NOW - timedelta(days=40), "stale-extra")
    rows = recent + [stale_extra]

    to_delete = plan_browse_trim_deletes(
        rows,
        max_per_user=max_per_user,
        retention_cutoff=_RETENTION_CUTOFF,
    )

    assert to_delete == {"stale-extra"}
