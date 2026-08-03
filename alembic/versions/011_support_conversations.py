"""011_support_conversations：support 域会话与消息表

- CREATE ``support_conversations``：id/shop_id/buyer_user_id/handler_mode/last_message_preview/created_at/updated_at
  UNIQUE(shop_id, buyer_user_id)、ix_support_conversations_shop_updated（(shop_id, updated_at)）
- CREATE ``support_messages``：id/conversation_id/sender_role/author_role/body/message_refs/created_at
  ix_support_messages_conversation_created（(conversation_id, created_at)）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("shop_id", sa.String(length=36), nullable=False),
        sa.Column("buyer_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "handler_mode",
            sa.String(length=16),
            server_default="human",
            nullable=False,
        ),
        sa.Column("last_message_preview", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_conversations")),
        sa.UniqueConstraint(
            "shop_id", "buyer_user_id", name=op.f("uq_support_conversations_shop_buyer")
        ),
    )
    op.create_index(
        "ix_support_conversations_shop_updated",
        "support_conversations",
        ["shop_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "support_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("sender_role", sa.String(length=16), nullable=False),
        sa.Column(
            "author_role",
            sa.String(length=16),
            server_default="human",
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("message_refs", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_messages")),
    )
    op.create_index(
        "ix_support_messages_conversation_created",
        "support_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_messages_conversation_created",
        table_name="support_messages",
    )
    op.drop_table("support_messages")
    op.drop_index(
        "ix_support_conversations_shop_updated",
        table_name="support_conversations",
    )
    op.drop_table("support_conversations")
