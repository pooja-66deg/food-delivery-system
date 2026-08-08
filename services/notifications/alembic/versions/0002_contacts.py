"""Contacts: how to reach a user, held by the service that sends to them.

Contact details used to travel on every order event, which meant every consumer
of that topic ended up with a copy — orders holding an email address it never
sends to. Personal data spreading for free is a poor default.

So the address lives here instead, in the one service whose job is contacting
people, fed by a topic only this service subscribes to. Order events now carry a
customer id and nothing more.

Revision ID: 0002_notifications_contacts
Revises: 0001_notifications_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_notifications_contacts"
down_revision = "0001_notifications_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        # The users service's id, so applying the same event twice is harmless.
        sa.Column("user_id", sa.Integer(), primary_key=True),
        # Both nullable: a user may have neither reachable, and a channel with
        # no address is a silent skip rather than a failure.
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contacts")
