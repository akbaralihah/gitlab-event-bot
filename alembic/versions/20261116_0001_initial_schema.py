"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-16 15:00:03.900523
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('gitlab_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gitlab_id', sa.BigInteger(), nullable=False),
    sa.Column('gitlab_username', sa.String(length=255), nullable=True),
    sa.Column('telegram_id', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gitlab_id'),
    sa.UniqueConstraint('gitlab_username'),
    sa.UniqueConstraint('telegram_id')
    )
    op.create_table('telegram_admins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('telegram_id', sa.BigInteger(), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('telegram_id')
    )
    op.create_table('telegram_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('chat_name', sa.String(length=255), nullable=False),
    sa.Column('chat_type', sa.String(length=50), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_forum', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('message_thread_id', sa.BigInteger(), nullable=True),
    sa.Column('message_thread_name', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('chat_id')
    )
    op.create_table('gitlab_projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('telegram_group_id', sa.Integer(), nullable=True),
    sa.Column('show_user', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('show_project', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('show_branch', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('show_status', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('show_duration', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.ForeignKeyConstraint(['telegram_group_id'], ['telegram_groups.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('gitlab_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gitlab_event', sa.String(length=20), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('branch', sa.String(length=255), nullable=False),
    sa.Column('user_name', sa.String(length=255), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['gitlab_projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('gitlab_users_projects',
    sa.Column('gitlabuser_id', sa.Integer(), nullable=False),
    sa.Column('gitlabproject_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['gitlabproject_id'], ['gitlab_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['gitlabuser_id'], ['gitlab_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('gitlabuser_id', 'gitlabproject_id')
    )


def downgrade() -> None:
    op.drop_table('gitlab_users_projects')
    op.drop_table('gitlab_events')
    op.drop_table('gitlab_projects')
    op.drop_table('telegram_groups')
    op.drop_table('telegram_admins')
    op.drop_table('gitlab_users')
