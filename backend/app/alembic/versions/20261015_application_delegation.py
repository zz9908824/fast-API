"""Add per-preparation delegation marker and materials."""

from alembic import op


revision = "20261015_app_delegation"
down_revision = "20261015_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE applications ADD COLUMN is_delegated boolean NOT NULL DEFAULT false;
    CREATE TABLE application_extra_materials (
      id uuid PRIMARY KEY,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      material_code varchar(80) NOT NULL,
      name varchar(200) NOT NULL,
      requirement_level varchar(16) NOT NULL DEFAULT 'required',
      declaration varchar(16) NOT NULL DEFAULT 'unknown',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(application_id, material_code),
      CONSTRAINT ck_app_extra_material_level CHECK (requirement_level IN ('required', 'optional')),
      CONSTRAINT ck_app_extra_material_declaration CHECK (declaration IN ('not_ready', 'ready', 'unknown'))
    );
    CREATE INDEX ix_application_extra_materials_application ON application_extra_materials(application_id);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE application_extra_materials;
    ALTER TABLE applications DROP COLUMN is_delegated;
    """)
