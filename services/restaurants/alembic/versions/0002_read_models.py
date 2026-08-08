"""Local read-model: what restaurants knows about an order.

Exists for one rule — "you may review an order you placed and that was
delivered". Both halves are the orders service's facts, and asking it per review
would make writing one fail whenever it is down.

Not authoritative. This service does not decide whether an order exists, only
what it was told about one.

Revision ID: 0002_restaurants_read_models
Revises: 0001_restaurants_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_restaurants_read_models"
down_revision = "0001_restaurants_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_snapshots",
        # The publisher's id, not a surrogate: one snapshot per order, and using
        # their id is what makes applying the same event twice harmless.
        sa.Column("order_id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(150), nullable=False, server_default=""),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # "Has this customer got a delivered order here?" is the review-eligibility
    # query, and it runs on every attempt to post one.
    op.create_index("ix_order_snapshots_customer_id", "order_snapshots", ["customer_id"])
    op.create_index("ix_order_snapshots_restaurant_id", "order_snapshots", ["restaurant_id"])

    # Denormalised onto the review rather than joined from a users table this
    # database does not have. Backfills empty: existing reviews predate the
    # split and have no name to recover, and a blank byline is better than a
    # wrong one.
    op.add_column(
        "reviews",
        sa.Column("reviewer_name", sa.String(150), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("reviews", "reviewer_name")
    op.drop_index("ix_order_snapshots_restaurant_id", table_name="order_snapshots")
    op.drop_index("ix_order_snapshots_customer_id", table_name="order_snapshots")
    op.drop_table("order_snapshots")
