"""Add order items and total to deliveries for driver display.

Drivers need to see what they're picking up and the order total.

Revision ID: 0007_delivery_order_items
Revises: 0006_delivery_order_details
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_delivery_order_items"
down_revision = "0006_delivery_order_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("items", sa.Text(), nullable=True),
    )
    op.add_column(
        "deliveries",
        sa.Column("order_total", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("deliveries", "items")
    op.drop_column("deliveries", "order_total")
