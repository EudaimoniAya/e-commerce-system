"""010_engagement_browse：user_browse_history 表

- CREATE ``user_browse_history``：id/user_id/product_id/first_viewed_at/last_viewed_at/view_count
- UNIQUE(user_id, product_id)、ix_user_browse_history_user_id_last_viewed（(user_id, last_viewed_at) ASC，
  MySQL 反向扫描等效 DESC，Alembic autogenerate 可正常比对）
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_browse_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("first_viewed_at", sa.DateTime(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(), nullable=False),
        sa.Column(
            "view_count", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_browse_history_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_browse_history")),
        sa.UniqueConstraint(
            "user_id", "product_id", name=op.f("uq_user_browse_history_user_id")
        ),
    )
    op.create_index(
        "ix_user_browse_history_user_id_last_viewed",
        "user_browse_history",
        ["user_id", "last_viewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_browse_history_user_id_last_viewed",
        table_name="user_browse_history",
    )
    op.drop_table("user_browse_history")
