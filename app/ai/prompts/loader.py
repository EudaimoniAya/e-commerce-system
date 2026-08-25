"""提示词加载器：按 id 读取 ``{base_dir}/{prompt_id}.yaml``（字段 id/version/template）。

契约（design D7）：
- 返回 ``LoadedPrompt``（``text``/``id``/``version``），供 LLM 调用日志带 prompt_id + version。
- 缺登记文件抛 ``PromptNotFoundError``，不得静默返回空串。
- 模板正文的变量填充（``{body}`` / ``{chunks}``）由调用方对 ``LoadedPrompt.text`` 执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class PromptNotFoundError(Exception):
    """提示词登记缺失：按 id 找不到对应 ``*.yaml``。"""


@dataclass(frozen=True)
class LoadedPrompt:
    """一份已登记的提示词：模板正文 + 登记元数据。"""

    text: str
    id: str
    version: str


class PromptLoader:
    """从 ``base_dir`` 下按 ``{prompt_id}.yaml`` 读取已登记提示词。"""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)

    def load(self, prompt_id: str) -> LoadedPrompt:
        """按 id 加载提示词；缺登记文件抛 ``PromptNotFoundError``。"""
        path = self._base_dir / f"{prompt_id}.yaml"
        if not path.is_file():
            raise PromptNotFoundError(f"提示词未登记: {prompt_id}（期望 {path}）")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return LoadedPrompt(
            text=data["template"],
            id=data["id"],
            version=data["version"],
        )
