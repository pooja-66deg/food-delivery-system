"""Restaurant approval status, food type, and an owner-name read-model.

Owners now register their own venue, so a restaurant existing and a restaurant
being allowed to trade stopped being the same fact. ``approval_status`` is that
second fact, and every customer-facing query filters on it.

**Existing rows are back-filled to 'approved', not 'pending'.** The default for
new rows is 'pending', but applying that default to rows already trading would
take every live restaurant off the platform the moment this migration ran —
an outage produced by a schema change, which is the worst kind to diagnose. A
venue that was already listed keeps trading; only registrations from here on
wait for an operator.

``food_type`` defaults to 'both', which is the honest answer for a restaurant
nobody has asked yet. 'veg' would be a claim the owner never made, and the
customer Vegetarian filter reads this column.

Revision ID: 0003_restaurants_approval
Revises: 0002_restaurants_read_models
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_restaurants_approval"
down_revision = "0002_restaurants_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default on the add, so the NOT NULL is satisfiable for existing
    # rows without a separate UPDATE pass.
    op.add_column(
        "restaurants",
        sa.Column(
            "approval_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("restaurants", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column(
        "restaurants",
        sa.Column("food_type", sa.String(10), nullable=False, server_default="both"),
    )

    # Grandfather everything that already existed — see the module docstring.
    # Runs before the index so it is one sequential pass, not an indexed update.
    op.execute("UPDATE restaurants SET approval_status = 'approved'")

    op.create_index("ix_restaurants_approval_status", "restaurants", ["approval_status"])
    op.create_index("ix_restaurants_food_type", "restaurants", ["food_type"])

    # The server_default has done its job. Dropping it makes the application the
    # only thing that decides a new restaurant's starting state, so the rule
    # cannot drift between here and create_restaurant().
    op.alter_column("restaurants", "approval_status", server_default=None)
    op.alter_column("restaurants", "food_type", server_default=None)

    op.create_table(
        "owner_rows",
        # No autoincrement: the id is the users service's id, copied in, never
        # minted here. Letting Postgres generate one would produce a sequence
        # that silently disagrees with the source of truth.
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("first_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("owner_rows")
    op.drop_index("ix_restaurants_food_type", table_name="restaurants")
    op.drop_index("ix_restaurants_approval_status", table_name="restaurants")
    op.drop_column("restaurants", "food_type")
    op.drop_column("restaurants", "rejection_reason")
    op.drop_column("restaurants", "approval_status")
