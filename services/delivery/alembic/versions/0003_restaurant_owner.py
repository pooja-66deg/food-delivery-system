"""Who owns a restaurant, so an owner action can be checked.

``reassign`` accepted any caller holding the restaurant role: the route's
``require_role("restaurant", "admin")`` says the caller is *a* restaurant, not
that they own *this* one, so any restaurant account could reassign the driver on
any order on the platform.

Checking it needs an owner id and the order's restaurant — neither of which this
service held. Both arrive by event: one integer copied is cheaper than a call to
the restaurants service on every owner action, and it does not fail when that
service is slow.

Revision ID: 0003_delivery_restaurant_owner
Revises: 0002_delivery_read_models
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_delivery_restaurant_owner"
down_revision = "0002_delivery_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "restaurant_snapshots",
        sa.Column("restaurant_id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_restaurant_snapshots_owner_id", "restaurant_snapshots", ["owner_id"])

    # Nullable: snapshots written before this revision have no restaurant, and
    # backfilling one would mean inventing it. They fill in on the next event.
    op.add_column("order_snapshots", sa.Column("restaurant_id", sa.Integer(), nullable=True))
    op.create_index("ix_order_snapshots_restaurant_id", "order_snapshots", ["restaurant_id"])


def downgrade() -> None:
    op.drop_index("ix_order_snapshots_restaurant_id", table_name="order_snapshots")
    op.drop_column("order_snapshots", "restaurant_id")
    op.drop_index("ix_restaurant_snapshots_owner_id", table_name="restaurant_snapshots")
    op.drop_table("restaurant_snapshots")
