"""Lower-case existing users.email, and stop two spellings of one address.

The application now normalises every inbound address (schemas._normalize_email),
but that only governs rows written from here on. Two things still needed doing:

- **Backfill.** Any row already stored with capitals cannot be found by a
  lookup that lower-cases first, so leaving them would lock exactly the accounts
  this fixes out of login *and* password recovery.
- **A functional unique index.** ``email`` is already unique, but Postgres
  compares it case-sensitively, so ``A@x.com`` and ``a@x.com`` both satisfy it
  while delivering to one mailbox. ``lower(email)`` is what makes "one address,
  one account" true in the database rather than only in the code.

The backfill can collide — that is the point of checking rather than assuming.
If two rows differ only by case, one of them cannot keep its address, and this
migration refuses rather than guessing which. Resolving it is a decision about
real accounts (which is the live one, does the other need merging), so it is
raised to an operator with the addresses named.

Revision ID: 0005_users_lower_email
Revises: 0004_users_password_reset

The id is abbreviated because alembic_version.version_num is varchar(32).
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_users_lower_email"
down_revision = "0004_users_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Refuse before writing anything, and name the addresses. A migration that
    # half-applied here would leave the table in a state nobody could reason
    # about — some rows folded, some not, and the index still missing.
    clashes = conn.execute(
        sa.text(
            """
            SELECT lower(email) AS folded, count(*) AS n,
                   string_agg(email, ', ' ORDER BY id) AS spellings
            FROM users
            GROUP BY lower(email)
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if clashes:
        detail = "; ".join(f"{r.folded} <- {r.spellings}" for r in clashes)
        raise RuntimeError(
            "Cannot fold users.email to lower case: these addresses differ only "
            f"by capitalisation and would collide: {detail}. Decide which account "
            "keeps the address (and whether the other needs merging), then re-run."
        )

    conn.execute(sa.text("UPDATE users SET email = lower(email) WHERE email <> lower(email)"))

    # Belt as well as braces: the column keeps its own unique constraint, and this
    # one makes the case-folded form unique too. Also the index a lower(email)
    # lookup can actually use.
    op.create_index(
        "uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True
    )


def downgrade() -> None:
    # The index goes; the folding does not come back. Original capitalisation was
    # not recorded anywhere, so there is nothing to restore it from — and an
    # address that works lower-cased keeps working, so leaving it folded is safe.
    op.drop_index("uq_users_email_lower", table_name="users")
