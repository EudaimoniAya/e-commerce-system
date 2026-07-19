"""顺序多步 orchestrator 的组合容器 PipelineResult。"""

from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PipelineResult:
    """线性 orchestrator 返回的步骤链。

    Attributes:
        steps: 各步 HTTP helper 的 ActionResult，按执行顺序排列。
    """

    steps: tuple[object, ...]

    def step(self, result_type: type[T]) -> T:
        """按精确类型取唯一一步。

        使用 ``type(item) is result_type`` 匹配（不用 ``isinstance``）。
        0 个或多个匹配时 raise ``LookupError``。
        """
        matches = self.all(result_type)
        if len(matches) != 1:
            raise LookupError(result_type)
        return matches[0]

    def all(self, result_type: type[T]) -> tuple[T, ...]:
        """返回 steps 中类型精确等于 ``result_type`` 的全部项。"""
        return tuple(item for item in self.steps if type(item) is result_type)
