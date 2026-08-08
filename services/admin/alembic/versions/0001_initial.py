"""Initial schema for the admin service — read-models only.

Every table here is a copy, kept current from events, and nothing else reads
this database. That is deliberate: an operator console reporting across the
whole platform either calls every service on every page load, or keeps its own
copy. The first makes it the most coupled thing on the platform; this is the
second.

Revision ID: 0001_admin_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_admin_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_rows",
        # The publisher's id, so applying the same event twice is harmless.
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(20), nullable=False, server_default=""),
        sa.Column("first_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "restaurant_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(150), nullable=False, server_default=""),
        sa.Column("owner_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "order_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=""),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default=""),
        # Numeric, never float: GMV is money.
        sa.Column("total", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_rows_customer_id", "order_rows", ["customer_id"])
    op.create_index("ix_order_rows_restaurant_id", "order_rows", ["restaurant_id"])
    # The stats page groups by status; the listing filters by it and sorts by
    # date. Both run on every load of the console's landing page.
    op.create_index("ix_order_rows_status", "order_rows", ["status"])
    op.create_index("ix_order_rows_created_at", "order_rows", ["created_at"])


def downgrade() -> None:
    op.drop_table("order_rows")
    op.drop_table("restaurant_rows")
    op.drop_table("user_rows")
