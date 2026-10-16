"""Store verified, versioned delegation rules and their materials."""

from alembic import op


revision = "20261015_delegation_policy"
down_revision = "20261015_app_delegation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE matter_delegation_policies (
      id uuid PRIMARY KEY,
      matter_version_id uuid NOT NULL UNIQUE REFERENCES matter_versions(id) ON DELETE RESTRICT,
      delegation_allowed boolean NOT NULL DEFAULT false,
      applicant_must_attend boolean NOT NULL DEFAULT false,
      relationship_required boolean NOT NULL DEFAULT false,
      allowed_relationships jsonb NOT NULL DEFAULT '[]'::jsonb,
      condition_expr jsonb NOT NULL DEFAULT '{"op":"always"}'::jsonb,
      questionnaire_required boolean NOT NULL DEFAULT false,
      verification_status varchar(20) NOT NULL DEFAULT 'pending',
      source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT,
      verified_by uuid REFERENCES "user"(id) ON DELETE RESTRICT,
      verified_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_delegation_relationships CHECK (jsonb_typeof(allowed_relationships) = 'array'),
      CONSTRAINT ck_delegation_condition CHECK (jsonb_typeof(condition_expr) = 'object'),
      CONSTRAINT ck_delegation_status CHECK (verification_status IN ('pending','verified','unavailable'))
    );
    CREATE TABLE matter_delegation_material_requirements (
      id uuid PRIMARY KEY,
      delegation_policy_id uuid NOT NULL REFERENCES matter_delegation_policies(id) ON DELETE RESTRICT,
      material_code varchar(80) NOT NULL, name varchar(200) NOT NULL,
      requirement_level varchar(16) NOT NULL DEFAULT 'required', submission_mode varchar(32) NOT NULL DEFAULT 'on_site',
      applicability_expr jsonb NOT NULL DEFAULT '{"op":"always"}'::jsonb,
      sort_order integer NOT NULL DEFAULT 0, verification_status varchar(20) NOT NULL DEFAULT 'pending',
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(delegation_policy_id, material_code),
      CONSTRAINT ck_delegation_material_level CHECK (requirement_level IN ('required','optional')),
      CONSTRAINT ck_delegation_material_mode CHECK (submission_mode IN ('user_upload','department_fetch','on_site','no_submission')),
      CONSTRAINT ck_delegation_material_expr CHECK (jsonb_typeof(applicability_expr) = 'object'),
      CONSTRAINT ck_delegation_material_status CHECK (verification_status IN ('pending','verified','unavailable'))
    );
    CREATE INDEX ix_delegation_material_policy ON matter_delegation_material_requirements(delegation_policy_id, sort_order);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE matter_delegation_material_requirements;
    DROP TABLE matter_delegation_policies;
    """)
