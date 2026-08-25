"""015_support_handler_mode_default_ai

ai-support-agent：lazy create 新会话默认 ``handler_mode=ai``。

- ``support_conversations.handler_mode`` server_default: ``human`` → ``ai``
- 既有库内 human 行**不迁移**（保持原值）

Revision ID: 9f4a6c2e8b1d
Revises: d3f7a1c9b4e2
Create Date: 2026-08-25 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f4a6c2e8b1d"
down_revision: str | None = "d3f7a1c9b4e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新会话默认 AI；既有行不变（仅改 server_default）。"""
    op.alter_column(
        "support_conversations",
        "handler_mode",
        server_default="ai",
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "support_conversations",
        "handler_mode",
        server_default="human",
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )
