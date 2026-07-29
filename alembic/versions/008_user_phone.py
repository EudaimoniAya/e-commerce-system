"""008_user_phone：phone 列、email/password_hash nullable

- ADD ``users.phone`` VARCHAR(20) UNIQUE NULL
- MODIFY ``users.email`` → NULL（初使 NOT NULL → NULL，MySQL 需 DROP → ADD）
- MODIFY ``users.password_hash`` → NULL（同上）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "ece9a7855313"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # 1. ADD phone（UNIQUE nullable）
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=20), nullable=True),
    )
    op.create_unique_constraint(op.f("uq_users_phone"), "users", ["phone"])

    # 2. MODIFY email → nullable
    # MySQL 不能直接 alter NOT NULL → NULL 若该列有 UNIQUE 且涉及已有行，
    # 用 DROP INDEX → MODIFY → ADD INDEX 模式
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])

    # 3. MODIFY password_hash → nullable
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # 4. 回填 admin 用户 phone（§3.2）
    _seed_admin_phone(connection)


def downgrade() -> None:
    # 1. MODIFY password_hash → NOT NULL（需先处理 NULL 行，否则失败）
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    # 2. MODIFY email → NOT NULL
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])

    # 3. DROP phone
    op.drop_constraint(op.f("uq_users_phone"), "users", type_="unique")
    op.drop_column("users", "phone")


def _seed_admin_phone(connection) -> None:
    """回填 seed 管理员 phone（migration 003 已插入的行）。"""
    connection.execute(
        sa.text(
            "UPDATE users SET phone = :phone WHERE email = :email"
        ),
        {"phone": "13800000000", "email": "114514yyut@qq.com"},
    )
