"""Record which extraction provider was selected for each import job."""

from alembic import op


revision = "20261015_import_provider"
down_revision = "20261013_matter_import_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE matter_import_jobs
      ADD COLUMN model_provider varchar(16) NOT NULL DEFAULT 'local',
      ADD CONSTRAINT ck_matter_import_model_provider CHECK (model_provider IN ('local', 'cloud'));
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE matter_import_jobs
      DROP CONSTRAINT ck_matter_import_model_provider,
      DROP COLUMN model_provider;
    """)
