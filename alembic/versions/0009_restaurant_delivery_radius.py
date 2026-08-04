"""restaurant delivery radius

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-04 20:41:03.118204
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and additive. NULL is not "unlimited": a geocoded restaurant that
    # never sets a radius falls back to DELIVERY_DEFAULT_RADIUS_KM, and one
    # without coordinates keeps the city-match behaviour it had before this
    # column existed. So no backfill is needed for existing rows to stay valid.
    op.add_column('restaurants', sa.Column('delivery_radius_km', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('restaurants', 'delivery_radius_km')
