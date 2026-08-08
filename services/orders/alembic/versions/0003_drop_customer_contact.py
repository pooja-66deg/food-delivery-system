"""Drop the customer contact columns.

They were a mistake worth undoing rather than living with. An address belongs in
the service that sends to it — notifications — and it now keeps its own contacts
read-model, fed by a topic only it subscribes to. Orders never contacts anyone,
so holding an email address here meant a second database storing personal data
for no reason at all.

The display name stays: the restaurants service puts it on a review byline, and
orders is the service that publishes the event carrying it.

Revision ID: 0003_orders_drop_contact
Revises: 0002_orders_read_models

Note the id length: Alembic stores it in a ``varchar(32)``, and a longer one
fails at the very end of the migration — after the schema change has already
been applied — leaving the version table behind the database.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_orders_drop_contact"
down_revision = "0002_orders_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("customer_snapshots", "email")
    op.drop_column("customer_snapshots", "phone")


def downgrade() -> None:
    # Restored empty. The data is not recoverable from here, and should not be:
    # if these are ever needed again they come from the users service's events.
    op.add_column("customer_snapshots", sa.Column("phone", sa.String(20), nullable=True))
    op.add_column("customer_snapshots", sa.Column("email", sa.String(255), nullable=True))
