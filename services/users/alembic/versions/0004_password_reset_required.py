"""Add users.password_reset_required.

Admin users can force a user to reset their password by setting this flag to true.
When a user logs in with this flag set, they must complete a password reset flow
before accessing other functionality.

Nullable=False with server_default='0' to maintain backward compatibility with
existing user records.

Revision ID: 0004_users_password_reset
Revises: 0003_users_approval

The id is abbreviated for the same reason as 0002: alembic_version.version_num
is varchar(32).
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_users_password_reset"
down_revision = "0003_users_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_reset_required")
