"""HTTP helper 用 ActionResult dataclass。"""

from dataclasses import dataclass

from app.catalog.schemas import CategoryCreate, CategoryResponse, ShopCreate, ShopResponse
from app.user.schemas import TokenResponse


@dataclass
class RegisterResult:
    """POST /auth/register 调用结果。"""

    status_code: int
    body: TokenResponse | None
    email: str
    password: str


@dataclass
class LoginResult:
    """POST /auth/login 调用结果。"""

    status_code: int
    body: TokenResponse | None
    email: str
    password: str


@dataclass
class ShopResult:
    """POST /shops 调用结果。"""

    status_code: int
    body: ShopResponse | None
    request: ShopCreate


@dataclass
class CategoryResult:
    """POST /categories 调用结果。"""

    status_code: int
    body: CategoryResponse | None
    request: CategoryCreate
