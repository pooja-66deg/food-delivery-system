"""menu item vegetarian flag

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-04 21:04:18.662901
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing items are unlabelled, and false is the safe reading of that: a
    # diner filtering for vegetarian food must not be shown a dish nobody has
    # confirmed. Owners opt each item in. The server default performs the
    # backfill, then goes away so the application owns the value.
    op.add_column(
        'menu_items',
        sa.Column('is_vegetarian', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column(
        'menu_items', 'is_vegetarian', existing_type=sa.Boolean(), server_default=None
    )

    # Discovery filters and sorts on the menu (dish-name search, price band,
    # vegetarian). Every one of those scans a restaurant's items.
    op.create_index('ix_menu_items_name', 'menu_items', ['name'])


def downgrade() -> None:
    op.drop_index('ix_menu_items_name', table_name='menu_items')
    op.drop_column('menu_items', 'is_vegetarian')
