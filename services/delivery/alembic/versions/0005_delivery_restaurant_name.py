"""Add restaurant name to deliveries for driver display.

Drivers need to see the restaurant name on their delivery card.
Copy it from the order snapshot when creating the delivery.

Revision ID: 0005_delivery_restaurant_name
Revises: 0004_delivery_restaurant_name
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_delivery_restaurant_name"
down_revision = "0004_delivery_restaurant_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("restaurant_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deliveries", "restaurant_name")
