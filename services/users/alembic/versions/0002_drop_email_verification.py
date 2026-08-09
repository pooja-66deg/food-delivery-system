"""Drop users.is_email_verified.

The email-verification flow is gone — the endpoints, the single-use token store
and the SPA page with it — so nothing writes this column and nothing reads it.
Left in place it would sit at ``false`` for every account forever, which reads
like "nobody has verified their address" rather than "the platform stopped
asking". That is a worse lie than an absent column.

The downgrade recreates it with ``server_default false`` rather than restoring
per-user values, because those values are not recoverable once the column is
dropped. Rolling back therefore gives a schema that matches revision 0001 and a
table where everyone appears unverified — correct as a schema, lossy as data.
Take a backup before applying this if the historical flags still matter to you.

Revision ID: 0002_users_drop_verified
Revises: 0001_users_initial

The id is abbreviated rather than spelled out in full: alembic_version.version_num
is varchar(32), and the obvious "0002_users_drop_email_verification" is 34
characters. Alembic does not check the length — Postgres raises
StringDataRightTruncation on the version bump *after* the DDL has run, and only
transactional DDL saves the schema from ending up ahead of the recorded version.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_users_drop_verified"
down_revision = "0001_users_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "is_email_verified")


def downgrade() -> None:
    # server_default, not default: an ORM-level default would leave the existing
    # rows null and the NOT NULL constraint would refuse the column.
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
