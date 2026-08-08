"""Initial schema for the notifications service.

The first service to be extracted, because nothing calls it synchronously — it
only consumes events. If it is down, no order fails; the events wait in Kafka
and are delivered when it comes back. That property is what makes it the safe
place to prove the whole pattern.

Every ``user_id`` here is a cross-service reference. That is not a gap to close
later: this service must be able to record and read a notification without
asking the users service anything, or it would inherit that service's downtime
and stop being independent.

Revision ID: 0001_notifications_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_notifications_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-service: users_db.
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        # Cross-service, and already a plain integer in the monolith.
        sa.Column("order_id", sa.Integer(), nullable=True),
        # Whether the send succeeded. Always true for a LOG row — writing it is
        # delivering it — and the provider's verdict for an outbound one, so a
        # failed SMS stays visible instead of vanishing into the log file.
        sa.Column("delivered", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_order_id", "notifications", ["order_id"])

    op.create_table(
        "notification_preferences",
        # One row per user, created on demand. The user id is the key here
        # rather than a foreign key to a table this database does not have.
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        # SMS is the one channel that costs per message and reaches people who
        # never asked for it, so it is opt-in rather than opt-out.
        sa.Column("sms_enabled", sa.Boolean(), nullable=False),
        sa.Column("push_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Unique on its own, so re-registering a token that moved between users
        # (a shared phone, a reinstall) re-points it rather than failing.
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_token", "device_tokens", ["token"], unique=True)

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_index("ix_device_tokens_token", table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")


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
