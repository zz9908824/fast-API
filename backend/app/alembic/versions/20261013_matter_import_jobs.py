"""Persist administrator matter-import candidates before draft creation."""

from alembic import op


revision = "20261013_matter_import_jobs"
down_revision = "20261012_finished_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE matter_import_jobs (
      id uuid PRIMARY KEY,
      initiated_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      status varchar(16) NOT NULL,
      region_code varchar(32) NOT NULL, region_name varchar(100) NOT NULL,
      source_url text NOT NULL, source_kind varchar(24) NOT NULL,
      source_title_override varchar(300), import_note text,
      input_text text NOT NULL, input_sha256 char(64) NOT NULL,
      candidate_json jsonb, error_message text,
      matter_version_id uuid REFERENCES matter_versions(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, applied_at timestamptz,
      CONSTRAINT ck_matter_import_status CHECK (status IN ('running', 'ready', 'failed', 'applied')),
      CONSTRAINT ck_matter_import_source_kind CHECK (source_kind IN ('policy', 'guide', 'template', 'faq', 'contact')),
      CONSTRAINT ck_matter_import_candidate CHECK (candidate_json IS NULL OR jsonb_typeof(candidate_json) = 'object'),
      CONSTRAINT ck_matter_import_sha CHECK (input_sha256 ~ '^[0-9a-fA-F]{64}$')
    );
    CREATE INDEX ix_matter_import_jobs_admin_created ON matter_import_jobs(initiated_by, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE matter_import_jobs;")
