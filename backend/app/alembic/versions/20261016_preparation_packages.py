"""Store immutable resident preparation-package snapshots."""

from alembic import op


revision = "20261016_preparation_packages"
down_revision = "20261015_material_review_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE preparation_packages (
      id uuid PRIMARY KEY,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      content_revision integer NOT NULL,
      package_no integer NOT NULL,
      snapshot_json jsonb NOT NULL,
      created_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(application_id, package_no),
      CONSTRAINT ck_preparation_package_snapshot CHECK (jsonb_typeof(snapshot_json) = 'object')
    );
    CREATE INDEX ix_preparation_packages_application_created
      ON preparation_packages(application_id, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE preparation_packages;")
