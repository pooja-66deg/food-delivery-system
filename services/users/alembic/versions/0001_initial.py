"""Initial schema for the users service.

Owns identity and the things that belong to a person rather than to a
transaction: their addresses, and the restaurants they have saved.

``favorites.restaurant_id`` is a plain integer, not a foreign key: restaurants
live in another database now and a foreign key cannot cross one. The pairing is
still enforced — the unique constraint is what stops a double-tap creating two
rows — but whether the restaurant exists is the application's job, answered from
the restaurant events this service consumes.

Revision ID: 0001_users_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_users_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_email_verified", sa.Boolean(), nullable=False),
        # Bumped by a password change or reset, which evicts every token minted
        # before it. Tokens carry the value they were signed with.
        sa.Column("session_generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Same database, so this one stays a real foreign key.
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("line1", sa.String(255), nullable=False),
        sa.Column("line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_addresses_user_id", "addresses", ["user_id"])

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        # Cross-service: restaurants live in restaurants_db.
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "restaurant_id", name="uq_favorite_user_restaurant"),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_index("ix_favorites_restaurant_id", "favorites", ["restaurant_id"])

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("favorites")
    op.drop_table("addresses")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")


def _create_outbox() -> None:
    """Every service gets its own outbox.

    A shared one would put all services back on a single table — one lock, one
    failure domain — which is the coupling being removed. Each service writes its
    events in the same transaction as its own state change and drains its own
    table.
    """
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("key", sa.String(100), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),  # JSON string
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    # The relay's hot query is "unpublished, oldest first".
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])
