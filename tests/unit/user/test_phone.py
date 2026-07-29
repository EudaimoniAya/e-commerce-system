"""app/user/phone.py 单元测试。"""

import allure

from app.user.phone import normalize_phone


@allure.epic("user")
@allure.feature("phone")
@allure.title("合法 11 位手机号原样返回。")
def test_normalize_11_digit_returns_normalized() -> None:
    """合法 11 位手机号原样返回。"""
    assert normalize_phone("13800138000") == "13800138000"


@allure.epic("user")
@allure.feature("phone")
@allure.title("+86 前缀被去除并返回规范化手机号。")
def test_normalize_with_plus86_prefix_strips_prefix() -> None:
    """+86 前缀被去除并返回规范化手机号。"""
    assert normalize_phone("+8613800138000") == "13800138000"


@allure.epic("user")
@allure.feature("phone")
@allure.title("86 前缀（无 +）被去除并返回规范化手机号。")
def test_normalize_with_86_prefix_strips_prefix() -> None:
    """86 前缀（无 +）被去除并返回规范化手机号。"""
    assert normalize_phone("8613800138000") == "13800138000"


@allure.epic("user")
@allure.feature("phone")
@allure.title("前后空格被去除。")
def test_normalize_with_spaces_strips_whitespace() -> None:
    """前后空格被去除。"""
    assert normalize_phone("  13800138000  ") == "13800138000"


@allure.epic("user")
@allure.feature("phone")
@allure.title("+86 前缀加空格组合。")
def test_normalize_with_plus86_and_spaces() -> None:
    """+86 前缀加空格组合。"""
    assert normalize_phone("  +86 13800138000  ") == "13800138000"


@allure.epic("user")
@allure.feature("phone")
@allure.title("少于 11 位返回 None。")
def test_normalize_too_short_returns_none() -> None:
    """少于 11 位返回 None。"""
    assert normalize_phone("1380013800") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("超过 11 位返回 None。")
def test_normalize_too_long_returns_none() -> None:
    """超过 11 位返回 None。"""
    assert normalize_phone("138001380000") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("非 1 开头的手机号返回 None。")
def test_normalize_invalid_start_digit_returns_none() -> None:
    """非 1 开头的手机号返回 None。"""
    assert normalize_phone("23800138000") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("第二位非 3-9 的手机号返回 None。")
def test_normalize_invalid_second_digit_returns_none() -> None:
    """第二位非 3-9 的手机号返回 None。"""
    assert normalize_phone("11000138000") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("空字符串返回 None。")
def test_normalize_empty_string_returns_none() -> None:
    """空字符串返回 None。"""
    assert normalize_phone("") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("含非数字字符（除 + 前缀外）返回 None。")
def test_normalize_contains_non_digit_returns_none() -> None:
    """含非数字字符（除 + 前缀外）返回 None。"""
    assert normalize_phone("1380013800a") is None


@allure.epic("user")
@allure.feature("phone")
@allure.title("86 开头但 86 非前缀的号码（如 86123456789 实为非法）返回 None。")
def test_normalize_invalid_prefix_86_then_valid_phone() -> None:
    """86 开头但 86 非前缀的号码（如 86123456789 实为非法）返回 None。

    86123456789 共 11 位，len 不大于 11 时不剥离 86，整体不匹配 pattern → None。
    """
    assert normalize_phone("86123456789") is None
