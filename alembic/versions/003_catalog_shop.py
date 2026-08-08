"""catalog-shop：users.is_admin、shops 表与 seed 管理员。"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from pwdlib import PasswordHash

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# migration seed 管理员凭据（仅开发/CI，见 design.md）
_ADMIN_SEED_EMAIL = "114514yyut@qq.com"
_ADMIN_SEED_PLAINTEXT_PASSWORD = "1919810810"
_ADMIN_SEED_NICKNAME = "平台管理员"

_hasher = PasswordHash.recommended()


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    """检查当前库中表列是否存在（兼容 Task 3.1 已先行应用 is_admin 的场景）。"""
    count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :table "
            "AND column_name = :column"
        ),
        {"table": table_name, "column": column_name},
    ).scalar()
    return bool(count)


def _table_exists(connection, table_name: str) -> bool:
    """检查当前库中表是否存在。"""
    count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :table"
        ),
        {"table": table_name},
    ).scalar()
    return bool(count)


def _seed_admin_user(connection) -> None:
    """插入或更新 seed 管理员（pwdlib 哈希）。"""
    password_hash = _hasher.hash(_ADMIN_SEED_PLAINTEXT_PASSWORD)
    admin_id = str(uuid.uuid4())
    connection.execute(
        sa.text(
            "INSERT INTO users "
            "(id, email, password_hash, nickname, is_active, is_admin) "
            "VALUES (:id, :email, :password_hash, :nickname, 1, 1) AS new_admin "
            "ON DUPLICATE KEY UPDATE "
            "password_hash = new_admin.password_hash, "
            "nickname = new_admin.nickname, "
            "is_admin = 1, is_active = 1"
        ),
        {
            "id": admin_id,
            "email": _ADMIN_SEED_EMAIL,
            "password_hash": password_hash,
            "nickname": _ADMIN_SEED_NICKNAME,
        },
    )


def upgrade() -> None:
    connection = op.get_bind()

    if not _column_exists(connection, "users", "is_admin"):
        op.add_column(
            "users",
            sa.Column(
                "is_admin",
                sa.Boolean(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )

    if not _table_exists(connection, "shops"):
        op.create_table(
            "shops",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("owner_user_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("logo_url", sa.String(length=512), nullable=True),
            sa.Column(
                "status",
                sa.String(length=16),
                server_default=sa.text("'active'"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["owner_user_id"],
                ["users.id"],
                name=op.f("fk_shops_owner_user_id_users"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_shops")),
            sa.UniqueConstraint("name", name=op.f("uq_shops_name")),
            sa.UniqueConstraint("owner_user_id", name=op.f("uq_shops_owner_user_id")),
        )

    _seed_admin_user(connection)


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM users WHERE email = :email"),
        {"email": _ADMIN_SEED_EMAIL},
    )
    if _table_exists(connection, "shops"):
        op.drop_table("shops")
    if _column_exists(connection, "users", "is_admin"):
        op.drop_column("users", "is_admin")
