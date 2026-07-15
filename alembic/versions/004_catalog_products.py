"""catalog-products：categories、products、product_categories 三表（无 seed）。"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
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
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint(
            "parent_id",
            "name",
            name=op.f("uq_categories_parent_id_name"),
        ),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("shop_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("image_url", sa.String(length=512), nullable=True),
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
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_products_shop_id_shops"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index(
        op.f("ix_products_shop_id"),
        "products",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_products_is_published"),
        "products",
        ["is_published"],
        unique=False,
    )

    op.create_table(
        "product_categories",
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_product_categories_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_categories_product_id_products"),
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "category_id",
            name=op.f("pk_product_categories"),
        ),
    )


def downgrade() -> None:
    op.drop_table("product_categories")
    op.drop_index(op.f("ix_products_is_published"), table_name="products")
    op.drop_index(op.f("ix_products_shop_id"), table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
