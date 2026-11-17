"""several topics per chat

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('telegram_groups_chat_id_key', 'telegram_groups', type_='unique')
    op.create_index(
        'uq_telegram_groups_chat_topic',
        'telegram_groups',
        ['chat_id', sa.text('coalesce(message_thread_id, 0)')],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_telegram_groups_chat_topic', table_name='telegram_groups')
    op.create_unique_constraint('telegram_groups_chat_id_key', 'telegram_groups', ['chat_id'])
