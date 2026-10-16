"""Preserve complete government-portal fields and extraction evidence."""

from alembic import op


revision = "20261015_gov_details"
down_revision = "20261015_import_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions
      ADD COLUMN government_profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      ADD COLUMN processing_steps_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD COLUMN legal_bases_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD COLUMN field_evidence_json jsonb NOT NULL DEFAULT '[]'::jsonb,
      ADD CONSTRAINT ck_matter_version_government_profile_json CHECK (jsonb_typeof(government_profile_json) = 'object'),
      ADD CONSTRAINT ck_matter_version_processing_steps_json CHECK (jsonb_typeof(processing_steps_json) = 'array'),
      ADD CONSTRAINT ck_matter_version_legal_bases_json CHECK (jsonb_typeof(legal_bases_json) = 'array'),
      ADD CONSTRAINT ck_matter_version_field_evidence_json CHECK (jsonb_typeof(field_evidence_json) = 'array');
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions
      DROP CONSTRAINT ck_matter_version_field_evidence_json,
      DROP CONSTRAINT ck_matter_version_legal_bases_json,
      DROP CONSTRAINT ck_matter_version_processing_steps_json,
      DROP CONSTRAINT ck_matter_version_government_profile_json,
      DROP COLUMN field_evidence_json,
      DROP COLUMN legal_bases_json,
      DROP COLUMN processing_steps_json,
      DROP COLUMN government_profile_json;
    """)
