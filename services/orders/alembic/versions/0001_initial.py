"""Initial schema for the orders service.

Owns the order itself, its lines, and the transition log behind them.

Note what ``order_items`` already does: it stores the dish's ``name`` and
``unit_price`` rather than pointing at a menu row. That was right in the
monolith — a receipt must not change when a restaurant edits its menu — and it
is exactly the pattern the split needs everywhere, because there is no menu
table in this database to join to.

Revision ID: 0001_orders_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_orders_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        # All three are cross-service: users_db, restaurants_db, users_db.
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("address_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("payment_status", sa.String(20), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("refund_status", sa.String(20), nullable=False),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("cancelled_by", sa.String(20), nullable=True),
        sa.Column("cancel_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_restaurant_id", "orders", ["restaurant_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        # Cross-service, and already a plain integer in the monolith: the line
        # carries its own name and price, so the menu row is a back-reference
        # rather than something to join to.
        sa.Column("menu_item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "order_status_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_status_events_order_id", "order_status_events", ["order_id"])

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("order_status_events")
    op.drop_table("order_items")
    op.drop_table("orders")


def _create_outbox() -> None:
    """This service's own outbox. See the users service for why it is per-service."""
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("key", sa.String(100), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])
