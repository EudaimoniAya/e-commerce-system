"""手机号规范化工具。

提供中国大陆手机号的格式化与校验，供 SMS OTP 流程使用。
Redis key 与 DB 存储均使用规范化后的 11 位手机号。
"""

import re

# 中国大陆手机号：1 开头，第二位 3-9，后接 9 位数字
_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


def normalize_phone(raw: str) -> str | None:
    """规范化手机号：去空格、去 +86/86 前缀，校验 11 位大陆手机号。

    Returns:
        规范化后的 11 位数字字符串，格式非法时返回 ``None``。
    """
    # 去除所有空白字符（含内部空格，如 "+86 138 0013 8000"）
    cleaned = "".join(raw.split())

    # 去除 +86 或 86 前缀
    if cleaned.startswith("+86"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("86") and len(cleaned) > 11:
        # 仅当 86 后面还有字符时才剥离，避免误伤 861... 开头的手机号
        cleaned = cleaned[2:]

    if _PHONE_PATTERN.match(cleaned):
        return cleaned
    return None
