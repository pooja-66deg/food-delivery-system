"""address coordinates

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04 09:41:12.503118
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and additive: every existing address stays valid and reads as
    # "not mappable", which is how they behaved before this column existed.
    op.add_column('addresses', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('addresses', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('addresses', 'longitude')
    op.drop_column('addresses', 'latitude')
