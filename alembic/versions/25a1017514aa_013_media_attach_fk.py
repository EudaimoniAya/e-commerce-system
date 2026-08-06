"""013_media_attach_fk

media-attach §1.1：业务表 FK 列替换 URL 列。

- users: +avatar_media_id FK → media_assets.id
- shops: +logo_media_id FK → media_assets.id, -logo_url
- products: +primary_media_id FK → media_assets.id, -image_url

Revision ID: 25a1017514aa
Revises: b4fffd14db3c
Create Date: 2026-08-06 21:44:50.281202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25a1017514aa'
down_revision: Union[str, None] = 'b4fffd14db3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users: avatar_media_id ──────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "avatar_media_id",
            sa.String(36),
            sa.ForeignKey("media_assets.id"),
            nullable=True,
        ),
    )

    # ── shops: logo_media_id + drop logo_url ────────────────────────────
    op.add_column(
        "shops",
        sa.Column(
            "logo_media_id",
            sa.String(36),
            sa.ForeignKey("media_assets.id"),
            nullable=True,
        ),
    )
    op.drop_column("shops", "logo_url")

    # ── products: primary_media_id + drop image_url ─────────────────────
    op.add_column(
        "products",
        sa.Column(
            "primary_media_id",
            sa.String(36),
            sa.ForeignKey("media_assets.id"),
            nullable=True,
        ),
    )
    op.drop_column("products", "image_url")


def downgrade() -> None:
    # ── products: 恢复 image_url, 删除 primary_media_id ─────────────────
    op.add_column(
        "products",
        sa.Column("image_url", sa.String(512), nullable=True),
    )
    op.drop_constraint(
        "fk_products_primary_media_id_media_assets",
        "products",
        type_="foreignkey",
    )
    op.drop_column("products", "primary_media_id")

    # ── shops: 恢复 logo_url, 删除 logo_media_id ────────────────────────
    op.add_column(
        "shops",
        sa.Column("logo_url", sa.String(512), nullable=True),
    )
    op.drop_constraint(
        "fk_shops_logo_media_id_media_assets",
        "shops",
        type_="foreignkey",
    )
    op.drop_column("shops", "logo_media_id")

    # ── users: 删除 avatar_media_id ─────────────────────────────────────
    op.drop_constraint(
        "fk_users_avatar_media_id_media_assets",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "avatar_media_id")
