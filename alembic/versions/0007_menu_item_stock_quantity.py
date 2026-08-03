"""menu item stock quantity

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-03 15:02:18.774310
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable with no default: existing items read as "stock not tracked",
    # which is exactly how they behaved before this column existed.
    op.add_column('menu_items', sa.Column('stock_quantity', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('menu_items', 'stock_quantity')
