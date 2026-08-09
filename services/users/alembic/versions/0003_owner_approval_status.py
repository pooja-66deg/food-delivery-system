"""Add users.approval_status.

A restaurant applicant now registers inactive and stays that way until an
operator approves their venue, so ``is_active`` alone stopped being enough to
explain a refused login. Inactive covers three different situations — waiting on
a decision, rejected, and deactivated long after being approved — and they need
different things said to them. Without this column the login route would have to
tell a rejected applicant they are "pending approval" forever.

Nullable, and null for everyone who is not a restaurant owner: a customer has no
application to have a status for, and a default of "approved" would read as a
decision somebody made rather than a question never asked. Existing restaurant
owners are backfilled to "approved" because they registered under the old rule,
where the account was live from the moment it was created — leaving them null
would lock out accounts that work today.

Revision ID: 0003_users_approval
Revises: 0002_users_drop_verified

The id is abbreviated for the same reason as 0002: alembic_version.version_num
is varchar(32).
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_users_approval"
down_revision = "0002_users_drop_verified"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("approval_status", sa.String(length=20), nullable=True),
    )
    # Backfill before anything reads it. Every restaurant account that exists at
    # this point predates the approval gate and is already trading, so "approved"
    # is the status that describes them — anything else revokes access that
    # people are using right now.
    op.execute(
        "UPDATE users SET approval_status = 'approved' WHERE role = 'restaurant'"
    )


def downgrade() -> None:
    # Dropping the column does not re-activate anyone: is_active is a separate
    # column and keeps whatever value approval left it with. An applicant who was
    # still pending stays locked out, which is the safe direction to fail — the
    # alternative is a downgrade that quietly admits unapproved venues.
    op.drop_column("users", "approval_status")
