"""notification preferences, device tokens, delivery outcome

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-04 20:52:41.907553
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows are all in-app (LOG) notifications, and writing one of those
    # *is* delivering it — so backfilling true is accurate, not a guess. Added
    # with a server default so the backfill and the NOT NULL land together, then
    # dropped: the application supplies the value from here on.
    op.add_column(
        'notifications',
        sa.Column('delivered', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column(
        'notifications', 'delivered', existing_type=sa.Boolean(), server_default=None
    )

    # One row per user, created on first write. A user with no row reads as the
    # defaults below, so absence is a valid state rather than missing data.
    op.create_table(
        'notification_preferences',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
    )

    # The token is unique platform-wide, not per user: the same device can move
    # between accounts, and re-registering re-points it.
    op.create_table(
        'device_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False, server_default='web'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_tokens_user_id', 'device_tokens', ['user_id'])
    op.create_index('ix_device_tokens_token', 'device_tokens', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_device_tokens_token', table_name='device_tokens')
    op.drop_index('ix_device_tokens_user_id', table_name='device_tokens')
    op.drop_table('device_tokens')
    op.drop_table('notification_preferences')
    op.drop_column('notifications', 'delivered')
