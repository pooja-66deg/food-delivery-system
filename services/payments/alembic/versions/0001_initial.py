"""Initial schema for the payments service.

One payment per order. ``idempotency_key`` is the important column in a
distributed setting: once calls cross a network they will be retried — by a
client, a gateway, or a Kafka consumer replaying — and this is what stops a
retry becoming a second charge.

Revision ID: 0001_payments_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_payments_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-service: the order lives in orders_db. Still unique — one
        # payment per order — which this service enforces alone.
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_ref", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=True)
    op.create_index(
        "ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True
    )

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_index("ix_payments_idempotency_key", table_name="payments")
    op.drop_index("ix_payments_order_id", table_name="payments")
    op.drop_table("payments")


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
