"""Local read-model: what payments knows about an order.

Authorising a charge needs the order's total and payment method. Asking the
orders service for them would mean a customer cannot pay whenever that service
is slow — on the one screen where failing is most expensive. The event carries
them instead.

Revision ID: 0002_payments_read_models
Revises: 0001_payments_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_payments_read_models"
down_revision = "0001_payments_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_snapshots",
        sa.Column("order_id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        # The amount to charge. Numeric, never float: a rounding error here is
        # money.
        sa.Column("total", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(20), nullable=False, server_default="COD"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # "My payments" is a per-customer read, and it is the only listing this
    # service serves.
    op.create_index("ix_order_snapshots_customer_id", "order_snapshots", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_order_snapshots_customer_id", table_name="order_snapshots")
    op.drop_table("order_snapshots")
