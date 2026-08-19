"""Weekly opening hours for restaurants.

Revision ID: 0004_restaurants_opening_hours
Revises: 0003_restaurants_approval

Complements ``restaurants.is_open`` rather than replacing it. Venues with no
rows keep the previous behaviour (manual switch alone).
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_restaurants_opening_hours"
down_revision = "0003_restaurants_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opening_hours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=True),
        sa.Column("closes_at", sa.Time(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("restaurant_id", "day_of_week", name="uq_opening_hours_day"),
    )
    op.create_index("ix_opening_hours_restaurant_id", "opening_hours", ["restaurant_id"])


def downgrade() -> None:
    op.drop_index("ix_opening_hours_restaurant_id", table_name="opening_hours")
    op.drop_table("opening_hours")
