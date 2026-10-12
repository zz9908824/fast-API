"""Add administrator verification tracking to material requirements."""

from alembic import op


revision = "20261012_material_verify"
down_revision = "20261012_social_card_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE material_requirements
      ADD COLUMN verification_status varchar(20) NOT NULL DEFAULT 'pending',
      ADD COLUMN verified_by uuid REFERENCES "user"(id) ON DELETE RESTRICT,
      ADD COLUMN verified_at timestamptz,
      ADD CONSTRAINT ck_material_requirement_verification
        CHECK (verification_status IN ('pending', 'verified', 'unavailable')),
      ADD CONSTRAINT ck_material_requirement_verified
        CHECK (verification_status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL));
    CREATE INDEX ix_material_requirements_verification
      ON material_requirements(matter_version_id, verification_status);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX ix_material_requirements_verification;
    ALTER TABLE material_requirements
      DROP CONSTRAINT ck_material_requirement_verified,
      DROP CONSTRAINT ck_material_requirement_verification,
      DROP COLUMN verified_at,
      DROP COLUMN verified_by,
      DROP COLUMN verification_status;
    """)
