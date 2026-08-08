"""Initial schema for the restaurants service.

Owns the catalogue — venues, their menus, and the reviews written about them.

Reviews sit here rather than with orders because the read that matters is "show
me this restaurant's rating", which happens on every listing. Putting them
beside the restaurant keeps that read inside one service; the alternative would
be a cross-service call on the busiest page in the product.

Revision ID: 0001_restaurants_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_restaurants_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-service: the owner is a user, in users_db.
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cuisine", sa.String(80), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("address_line", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        # NULL means "not set" and falls back to the platform default, not to
        # unlimited.
        sa.Column("delivery_radius_km", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_restaurants_owner_id", "restaurants", ["owner_id"])
    op.create_index("ix_restaurants_name", "restaurants", ["name"])
    op.create_index("ix_restaurants_city", "restaurants", ["city"])

    op.create_table(
        "menu_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_menu_categories_restaurant_id", "menu_categories", ["restaurant_id"])

    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("menu_categories.id"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        # The owner's manual switch. Never rewritten by the system, so "turned
        # off" stays distinguishable from "sold out".
        sa.Column("is_available", sa.Boolean(), nullable=False),
        # NULL means stock is not tracked for this item.
        sa.Column("stock_quantity", sa.Integer(), nullable=True),
        # Not nullable: "unknown" and "not vegetarian" must give the same answer,
        # or a diner filtering for vegetarian food gets shown an unlabelled dish.
        sa.Column("is_vegetarian", sa.Boolean(), nullable=False),
        sa.Column("image_url", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])
    op.create_index("ix_menu_items_category_id", "menu_items", ["category_id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Cross-service: the order lives in orders_db. Still unique — one review
        # per order — which this service can enforce alone.
        sa.Column("order_id", sa.Integer(), nullable=False),
        # Cross-service: the author is a user, in users_db.
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),  # 1..5
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("owner_reply", sa.String(1000), nullable=True),
        sa.Column("owner_replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # NULL means never edited — not "edited at creation time", which is what
        # defaulting to now() would imply.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reviews_order_id", "reviews", ["order_id"], unique=True)
    op.create_index("ix_reviews_customer_id", "reviews", ["customer_id"])
    op.create_index("ix_reviews_restaurant_id", "reviews", ["restaurant_id"])

    _create_outbox()


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("reviews")
    op.drop_table("menu_items")
    op.drop_table("menu_categories")
    op.drop_table("restaurants")


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
