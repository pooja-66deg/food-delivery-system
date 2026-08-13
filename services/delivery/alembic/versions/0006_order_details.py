"""Add order details to snapshots for driver visibility.

Drivers need to see what they're picking up (items), how much the order costs,
the customer name, and the delivery address before accepting a delivery.

Revision ID: 0006_delivery_order_details
Revises: 0005_delivery_restaurant_name
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_delivery_order_details"
down_revision = "0005_delivery_restaurant_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_snapshots",
        sa.Column("customer_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "order_snapshots",
        sa.Column("items", sa.Text(), nullable=True),
    )
    op.add_column(
        "order_snapshots",
        sa.Column("order_total", sa.String(20), nullable=True),
    )
    op.add_column(
        "order_snapshots",
        sa.Column("delivery_address", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_snapshots", "customer_name")
    op.drop_column("order_snapshots", "items")
    op.drop_column("order_snapshots", "order_total")
    op.drop_column("order_snapshots", "delivery_address")
