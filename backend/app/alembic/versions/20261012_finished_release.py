"""Allow the reviewed, publicly available matter-version status ``finished``.

Revision ID: 20261012_finished_release
Revises: 20261012_material_verify
"""

from alembic import op


revision = "20261012_finished_release"
down_revision = "20261012_material_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions DROP CONSTRAINT ck_matter_version_status;
    ALTER TABLE matter_versions DROP CONSTRAINT ck_matter_version_published;
    ALTER TABLE matter_versions
      ADD CONSTRAINT ck_matter_version_status
      CHECK (status IN ('draft', 'finished', 'published', 'retired'));
    ALTER TABLE matter_versions
      ADD CONSTRAINT ck_matter_version_finished
      CHECK (status NOT IN ('finished', 'published') OR (approved_by IS NOT NULL AND published_at IS NOT NULL));
    """)


def downgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions DROP CONSTRAINT ck_matter_version_finished;
    ALTER TABLE matter_versions DROP CONSTRAINT ck_matter_version_status;
    ALTER TABLE matter_versions
      ADD CONSTRAINT ck_matter_version_status
      CHECK (status IN ('draft', 'published', 'retired'));
    ALTER TABLE matter_versions
      ADD CONSTRAINT ck_matter_version_published
      CHECK (status <> 'published' OR (approved_by IS NOT NULL AND published_at IS NOT NULL));
    """)
