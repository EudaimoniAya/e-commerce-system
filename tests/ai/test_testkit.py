"""AI testkit 目录占位测试。

覆盖 spec fake-providers「AI domain testkit directory exists」：
- tests/ai/testkit/ 存在且至少有一个可被 git 跟踪的文件（.gitkeep 或替身模块）。
"""

from pathlib import Path

import allure


@allure.epic("ai")
@allure.feature("testkit")
@allure.title("tests/ai/testkit 目录含可跟踪文件。")
def test_ai_testkit_dir_has_trackable_file() -> None:
    """testkit 目录存在且含至少一个文件（.gitkeep 或替身模块）。"""
    testkit = Path(__file__).resolve().parent / "testkit"
    assert testkit.is_dir()
    assert any(p.is_file() for p in testkit.iterdir())
