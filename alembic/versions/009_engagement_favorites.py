"""009_engagement_favorites：user_favorites 表

- CREATE ``user_favorites``：id/user_id/product_id/created_at
- UNIQUE(user_id, product_id)、ix_user_favorites_user_id
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_favorites_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_favorites")),
        sa.UniqueConstraint(
            "user_id", "product_id", name=op.f("uq_user_favorites_user_id")
        ),
    )
    op.create_index(
        "ix_user_favorites_user_id", "user_favorites", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_favorites_user_id", table_name="user_favorites")
    op.drop_table("user_favorites")
