"""Add the P0 concurrency and interaction fields used by the precheck API."""

from alembic import op


revision = "20261010_precheck_api"
down_revision = "20261010_gov_precheck"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE matter_versions ADD COLUMN config_revision integer NOT NULL DEFAULT 1
      CHECK (config_revision > 0);
    ALTER TABLE material_requirements ADD COLUMN alternative_group_code varchar(80);
    ALTER TABLE applications ADD COLUMN questionnaire_status varchar(16) NOT NULL DEFAULT 'draft'
      CHECK (questionnaire_status IN ('draft', 'submitted'));
    ALTER TABLE check_runs ADD COLUMN coverage varchar(16) NOT NULL DEFAULT 'full'
      CHECK (coverage IN ('full', 'partial'));
    ALTER TABLE check_runs ADD COLUMN input_preparation_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE extraction_runs ADD COLUMN input_schema_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE review_tasks ADD COLUMN task_revision integer NOT NULL DEFAULT 1
      CHECK (task_revision > 0);
    ALTER TABLE review_records ADD COLUMN details jsonb NOT NULL DEFAULT '{}'::jsonb;

    CREATE TABLE application_preparation_items (
      id uuid PRIMARY KEY,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      requirement_id uuid NOT NULL REFERENCES material_requirements(id) ON DELETE RESTRICT,
      participant_id uuid REFERENCES application_participants(id) ON DELETE RESTRICT,
      declaration varchar(16) NOT NULL DEFAULT 'unknown',
      declared_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_preparation_declaration CHECK (declaration IN ('not_ready', 'ready', 'unknown'))
    );
    CREATE UNIQUE INDEX uq_preparation_item_participant
      ON application_preparation_items(application_id, requirement_id, participant_id)
      WHERE participant_id IS NOT NULL;
    CREATE UNIQUE INDEX uq_preparation_item_no_participant
      ON application_preparation_items(application_id, requirement_id)
      WHERE participant_id IS NULL;

    CREATE TABLE review_task_messages (
      id uuid PRIMARY KEY,
      task_id uuid NOT NULL REFERENCES review_tasks(id) ON DELETE RESTRICT,
      message_no integer NOT NULL,
      actor_user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      sender_kind varchar(16) NOT NULL,
      body varchar(4000) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(task_id, message_no),
      CONSTRAINT ck_review_message_sender CHECK (sender_kind IN ('user', 'staff')),
      CONSTRAINT ck_review_message_body CHECK (btrim(body) <> '')
    );

    CREATE TABLE api_idempotency_records (
      id uuid PRIMARY KEY,
      user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      operation varchar(120) NOT NULL,
      idempotency_key varchar(255) NOT NULL,
      request_hash char(64) NOT NULL,
      state varchar(16) NOT NULL DEFAULT 'completed',
      resource_id uuid,
      response_status smallint,
      response_json jsonb,
      expires_at timestamptz NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(user_id, operation, idempotency_key),
      CONSTRAINT ck_idempotency_state CHECK (state IN ('in_progress', 'completed'))
    );
    CREATE INDEX ix_idempotency_expires ON api_idempotency_records(expires_at);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE api_idempotency_records;
    DROP TABLE review_task_messages;
    DROP INDEX uq_preparation_item_no_participant;
    DROP INDEX uq_preparation_item_participant;
    DROP TABLE application_preparation_items;
    ALTER TABLE review_records DROP COLUMN details;
    ALTER TABLE review_tasks DROP COLUMN task_revision;
    ALTER TABLE extraction_runs DROP COLUMN input_schema_snapshot;
    ALTER TABLE check_runs DROP COLUMN input_preparation_snapshot;
    ALTER TABLE check_runs DROP COLUMN coverage;
    ALTER TABLE applications DROP COLUMN questionnaire_status;
    ALTER TABLE material_requirements DROP COLUMN alternative_group_code;
    ALTER TABLE matter_versions DROP COLUMN config_revision;
    """)
