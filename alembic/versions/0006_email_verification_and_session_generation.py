"""email verification flag and session generation

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03 10:12:41.203118
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Server defaults so the NOT NULL columns can be added to a populated table.
    op.add_column(
        'users',
        sa.Column('is_email_verified', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('session_generation', sa.Integer(), nullable=False,
                  server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('users', 'session_generation')
    op.drop_column('users', 'is_email_verified')
