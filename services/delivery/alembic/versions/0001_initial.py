"""Initial schema for the delivery service.

One delivery per order, one active order per driver.

``driver_id`` stays nullable — UNASSIGNED is a real state, reached when an order
is ready and no driver is free. Note that "which drivers are free" is answered
by querying this table, not the users table: availability is a delivery concept,
so the split leaves that query inside this service rather than making it a
cross-service call on every assignment.

Revision ID: 0001_delivery_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_delivery_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-service: the order lives in orders_db.
        sa.Column("order_id", sa.Integer(), nullable=False),
        # Cross-service: the driver is a user, in users_db. Nullable because
        # UNASSIGNED — no driver free yet — is a legitimate state.
        sa.Column("driver_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deliveries_order_id", "deliveries", ["order_id"], unique=True)
    op.create_index("ix_deliveries_driver_id", "deliveries", ["driver_id"])
    # The availability query is "active deliveries, by driver" and runs on every
    # assignment; on its own, the driver_id index still makes it scan every one
    # of that driver's historical deliveries.
    op.create_index("ix_deliveries_status_driver", "deliveries", ["status", "driver_id"])

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_index("ix_deliveries_status_driver", table_name="deliveries")
    op.drop_index("ix_deliveries_driver_id", table_name="deliveries")
    op.drop_index("ix_deliveries_order_id", table_name="deliveries")
    op.drop_table("deliveries")


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
