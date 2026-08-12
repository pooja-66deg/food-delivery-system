"""Add restaurant name to order snapshots for driver notifications.

Drivers need to see which restaurant an order is from when they get a delivery
offer. Restaurant name arrives in order events, so we copy it here like we do
with coordinates.

Revision ID: 0004_delivery_restaurant_name
Revises: 0003_delivery_restaurant_owner
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_delivery_restaurant_name"
down_revision = "0003_delivery_restaurant_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_snapshots",
        sa.Column("restaurant_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_snapshots", "restaurant_name")
