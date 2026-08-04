"""review edits and owner replies, favourite restaurants

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-04 21:19:52.441077
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All nullable: an existing review has never been edited and has no reply,
    # which is exactly what NULL says in each column. No backfill — defaulting
    # updated_at to created_at would make every old review read as edited.
    op.add_column('reviews', sa.Column('owner_reply', sa.String(length=1000), nullable=True))
    op.add_column('reviews', sa.Column('owner_replied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('reviews', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id']),
        sa.PrimaryKeyConstraint('id'),
        # Favouriting twice must not duplicate, and enforcing it here means two
        # concurrent taps cannot both pass an application-level check.
        sa.UniqueConstraint('user_id', 'restaurant_id', name='uq_favorite_user_restaurant'),
    )
    op.create_index('ix_favorites_user_id', 'favorites', ['user_id'])
    op.create_index('ix_favorites_restaurant_id', 'favorites', ['restaurant_id'])


def downgrade() -> None:
    op.drop_index('ix_favorites_restaurant_id', table_name='favorites')
    op.drop_index('ix_favorites_user_id', table_name='favorites')
    op.drop_table('favorites')
    op.drop_column('reviews', 'updated_at')
    op.drop_column('reviews', 'owner_replied_at')
    op.drop_column('reviews', 'owner_reply')
