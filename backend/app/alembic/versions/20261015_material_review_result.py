"""Persist structured AI material-review results for each check run."""

from alembic import op


revision = "20261015_material_review_result"
down_revision = "20261015_delegation_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE check_runs ADD COLUMN model_result_json jsonb NOT NULL DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE check_runs DROP COLUMN model_result_json")
