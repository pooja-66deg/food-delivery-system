"""Local read-models: what delivery knows about orders and drivers.

Neither table is authoritative. They are copies, kept current by consuming the
orders and users services' events, and they exist so that assigning and
navigating a delivery needs nothing but this database. Calling those services
instead would mean a delivery cannot be assigned while they are down.

A read-model is therefore allowed to be a little behind. The columns reflect
that: everything a publisher might not have sent yet is nullable, so a partial
copy is a usable copy rather than a failed insert.

Revision ID: 0002_delivery_read_models
Revises: 0001_delivery_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_delivery_read_models"
down_revision = "0001_delivery_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_snapshots",
        # The order's own id, not a surrogate: there is exactly one snapshot per
        # order, and using the publisher's id makes an event idempotent to apply.
        sa.Column("order_id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        # Copied, not referenced. A driver must be able to navigate while the
        # restaurants and users services are unavailable.
        sa.Column("restaurant_latitude", sa.Float(), nullable=True),
        sa.Column("restaurant_longitude", sa.Float(), nullable=True),
        sa.Column("destination_latitude", sa.Float(), nullable=True),
        sa.Column("destination_longitude", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # "Who can I offer this to" is the query that runs on every assignment.
    op.create_index("ix_drivers_is_active", "drivers", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_drivers_is_active", table_name="drivers")
    op.drop_table("drivers")
    op.drop_table("order_snapshots")
