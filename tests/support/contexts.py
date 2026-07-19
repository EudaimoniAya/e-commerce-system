"""Setup fixture 用 Context dataclass（极薄，仅持有 PipelineResult）。"""

from dataclasses import dataclass

from tests.support.pipeline import PipelineResult


@dataclass(frozen=True)
class AuthContext:
    """注册用户 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        root: 含 ``RegisterResult`` 的 Pipeline（通常仅一步）。
    """

    root: PipelineResult


@dataclass(frozen=True)
class AdminAuthContext:
    """seed 管理员登录后的 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        root: 含 ``LoginResult`` 的 Pipeline（通常仅一步）。
    """

    root: PipelineResult


@dataclass(frozen=True)
class ShopOwnerContext:
    """注册并开店成功后的 Setup 上下文（fail-fast 后的世界）。

    Attributes:
        root: 含 ``RegisterResult`` 与 ``ShopResult`` 的 Pipeline。
    """

    root: PipelineResult
