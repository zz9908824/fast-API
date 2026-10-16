"""Allow a resident to label only their own preparation record."""

from alembic import op


revision = "20261016_app_display_name"
down_revision = "20261016_preparation_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applications ADD COLUMN display_name varchar(200);")


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP COLUMN display_name;")
