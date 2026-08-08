"""Local read-model: where an order can be delivered.

Checkout has to ask the restaurants service "do you deliver to this point?", and
that question needs a city and a pair of coordinates. Fetching them from the
users service per checkout would put a second synchronous dependency on the one
request that must not fail — so they arrive by event instead, and checkout keeps
exactly one sync call.

City and coordinates only. This service has no use for a street line, and a
read-model that copies more than it uses is personal data spreading for free.

Revision ID: 0002_orders_read_models
Revises: 0001_orders_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_orders_read_models"
down_revision = "0001_orders_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "address_snapshots",
        # The publisher's id, so applying the same event twice is harmless.
        sa.Column("address_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(100), nullable=False, server_default=""),
        # Nullable: an address that never geocoded still orders, it just falls
        # back to a city match for the zone check.
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Checkout looks an address up by id and then checks it belongs to the
    # caller; the index serves "my addresses" style reads.
    op.create_index("ix_address_snapshots_user_id", "address_snapshots", ["user_id"])

    op.create_table(
        "customer_snapshots",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(150), nullable=False, server_default=""),
        # Dropped again in 0003: contact details belong in the notifications
        # service, which is the only one that sends to them.
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "restaurant_snapshots",
        sa.Column("restaurant_id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # "Which of my restaurants' orders are these?" is the owner dashboard's
    # first question on every load.
    op.create_index("ix_restaurant_snapshots_owner_id", "restaurant_snapshots", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_restaurant_snapshots_owner_id", table_name="restaurant_snapshots")
    op.drop_table("restaurant_snapshots")
    op.drop_table("customer_snapshots")
    op.drop_index("ix_address_snapshots_user_id", table_name="address_snapshots")
    op.drop_table("address_snapshots")
