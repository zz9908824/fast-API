"""Add structured source metadata for social-card configuration."""

from alembic import op


revision = "20261012_social_card_metadata"
down_revision = "20261010_precheck_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions ADD COLUMN metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
      CHECK (jsonb_typeof(metadata_json) = 'object');
    ALTER TABLE applications ADD COLUMN form_data jsonb NOT NULL DEFAULT '{}'::jsonb
      CHECK (jsonb_typeof(form_data) = 'object');
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE applications DROP COLUMN form_data;
    ALTER TABLE matter_versions DROP COLUMN metadata_json;
    """)
