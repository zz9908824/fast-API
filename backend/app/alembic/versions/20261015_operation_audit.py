"""Store current-user administrator operation records."""

from alembic import op


revision = "20261015_audit_log"
down_revision = "20261015_gov_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE operation_audit_logs (
      id uuid PRIMARY KEY, actor_user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      category varchar(40) NOT NULL, action varchar(100) NOT NULL,
      target_type varchar(60) NOT NULL, target_id uuid, target_name varchar(300),
      details_json jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_operation_audit_details CHECK (jsonb_typeof(details_json) = 'object')
    );
    CREATE INDEX ix_operation_audit_actor_created ON operation_audit_logs(actor_user_id, created_at DESC);
    CREATE INDEX ix_operation_audit_actor_category ON operation_audit_logs(actor_user_id, category, created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE operation_audit_logs;")
