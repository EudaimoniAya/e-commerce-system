"""从 *Result 投影请求头等纯函数（无 HTTP/DB）。"""

from typing import Protocol

from app.user.schemas import TokenResponse


class _HasTokenBody(Protocol):
    """含 ``TokenResponse`` body 的 Result（如 RegisterResult / LoginResult）。"""

    body: TokenResponse | None


def bearer_headers(result: _HasTokenBody) -> dict[str, str]:
    """从含 ``access_token`` 的 Result 投影 Bearer Authorization 请求头。

    Raises:
        ValueError: ``result.body`` 为 ``None`` 时无法投影。
    """
    if result.body is None:
        msg = "result.body 为 None，无法投影 Bearer headers"
        raise ValueError(msg)
    return {"Authorization": f"Bearer {result.body.access_token}"}
