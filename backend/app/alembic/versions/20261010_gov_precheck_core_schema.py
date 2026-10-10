"""Create the core schema for the government-material precheck service.

The authentication table is intentionally not recreated: this project already
uses the SQLModel table named ``user``.  All account foreign keys target it.
"""

from alembic import op


revision = "20261010_gov_precheck"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Configuration: matters, sources, material catalogues and immutable versions.
    op.execute("""
    CREATE TABLE service_matters (
      id uuid PRIMARY KEY, code varchar(100) NOT NULL UNIQUE,
      official_code varchar(150), name varchar(200) NOT NULL,
      region_code varchar(32) NOT NULL, region_name varchar(100) NOT NULL,
      description text, is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_service_matter_name CHECK (btrim(name) <> '')
    );
    CREATE INDEX ix_service_matters_region_active ON service_matters(region_code, is_active);

    CREATE TABLE policy_sources (
      id uuid PRIMARY KEY, title varchar(300) NOT NULL,
      source_kind varchar(24) NOT NULL, url text NOT NULL, publisher varchar(200),
      published_date date, retrieved_at timestamptz NOT NULL DEFAULT now(), content_text text,
      content_sha256 char(64), verification_status varchar(20) NOT NULL DEFAULT 'pending',
      verified_by uuid REFERENCES "user"(id) ON DELETE RESTRICT, verified_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_policy_source_kind CHECK (source_kind IN ('policy','guide','template','faq','contact')),
      CONSTRAINT ck_policy_verification CHECK (verification_status IN ('pending','verified','unavailable')),
      CONSTRAINT ck_policy_verified CHECK (verification_status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)),
      CONSTRAINT ck_policy_sha256 CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-fA-F]{64}$')
    );
    CREATE INDEX ix_policy_sources_status_retrieved ON policy_sources(verification_status, retrieved_at);

    CREATE TABLE material_types (
      id uuid PRIMARY KEY, code varchar(80) NOT NULL UNIQUE, name varchar(150) NOT NULL,
      description text, is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE service_locations (
      id uuid PRIMARY KEY, name varchar(200) NOT NULL, region_code varchar(32) NOT NULL,
      address text, phone varchar(100), opening_hours text, official_entry_url text,
      source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT,
      verification_status varchar(20) NOT NULL DEFAULT 'pending', checked_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_location_verification CHECK (verification_status IN ('pending','verified','unavailable')),
      CONSTRAINT ck_location_checked CHECK (verification_status <> 'verified' OR checked_at IS NOT NULL)
    );

    CREATE TABLE matter_versions (
      id uuid PRIMARY KEY, matter_id uuid NOT NULL REFERENCES service_matters(id) ON DELETE RESTRICT,
      version_no integer NOT NULL, status varchar(20) NOT NULL DEFAULT 'draft',
      valid_from date, valid_to date, change_summary text, source_checked_at timestamptz,
      service_location_id uuid REFERENCES service_locations(id) ON DELETE RESTRICT,
      created_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      approved_by uuid REFERENCES "user"(id) ON DELETE RESTRICT, published_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(matter_id, version_no), UNIQUE(id, matter_id),
      CONSTRAINT ck_matter_version_no CHECK (version_no > 0),
      CONSTRAINT ck_matter_version_status CHECK (status IN ('draft','published','retired')),
      CONSTRAINT ck_matter_version_dates CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from),
      CONSTRAINT ck_matter_version_published CHECK (status <> 'published' OR (approved_by IS NOT NULL AND published_at IS NOT NULL))
    );
    CREATE INDEX ix_matter_versions_matter_status ON matter_versions(matter_id, status, version_no);
    CREATE INDEX ix_matter_versions_location ON matter_versions(service_location_id);

    CREATE TABLE material_requirements (
      id uuid PRIMARY KEY, matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      material_type_id uuid NOT NULL REFERENCES material_types(id) ON DELETE RESTRICT,
      requirement_code varchar(80) NOT NULL, name varchar(200) NOT NULL,
      applicability_expr jsonb NOT NULL DEFAULT '{"op":"always"}'::jsonb,
      requirement_level varchar(20) NOT NULL DEFAULT 'required', provider_role varchar(32),
      submission_mode varchar(32) NOT NULL DEFAULT 'user_upload', original_required boolean,
      copy_count smallint, min_pages smallint, format_requirements text,
      template_source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT,
      field_schema jsonb NOT NULL DEFAULT '{"fields":[]}'::jsonb, sort_order integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(matter_version_id, requirement_code), UNIQUE(id, matter_version_id),
      CONSTRAINT ck_requirement_level CHECK (requirement_level IN ('required','optional')),
      CONSTRAINT ck_requirement_submission CHECK (submission_mode IN ('user_upload','department_fetch','on_site','no_submission')),
      CONSTRAINT ck_requirement_counts CHECK ((copy_count IS NULL OR copy_count >= 0) AND (min_pages IS NULL OR min_pages > 0)),
      CONSTRAINT ck_requirement_json CHECK (jsonb_typeof(applicability_expr) = 'object' AND jsonb_typeof(field_schema) = 'object')
    );
    CREATE INDEX ix_material_requirements_version_order ON material_requirements(matter_version_id, sort_order);
    CREATE INDEX ix_material_requirements_type ON material_requirements(material_type_id);

    CREATE TABLE material_acquisition_methods (
      id uuid PRIMARY KEY, requirement_id uuid NOT NULL REFERENCES material_requirements(id) ON DELETE RESTRICT,
      method_code varchar(80) NOT NULL, method_type varchar(30) NOT NULL, title varchar(200) NOT NULL,
      steps text, entry_url text, location_id uuid REFERENCES service_locations(id) ON DELETE RESTRICT,
      source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT,
      applicability_expr jsonb NOT NULL DEFAULT '{"op":"always"}'::jsonb,
      verification_status varchar(20) NOT NULL DEFAULT 'pending', sort_order integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(requirement_id, method_code),
      CONSTRAINT ck_acquisition_type CHECK (method_type IN ('online_download','online_apply','in_person','self_prepare','department_fetch','on_site')),
      CONSTRAINT ck_acquisition_verification CHECK (verification_status IN ('pending','verified','unavailable'))
    );

    CREATE TABLE verification_rules (
      id uuid PRIMARY KEY, matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      rule_code varchar(80) NOT NULL, name varchar(200) NOT NULL, rule_type varchar(24) NOT NULL,
      applicability_expr jsonb NOT NULL DEFAULT '{"op":"always"}'::jsonb, input_spec jsonb NOT NULL DEFAULT '{}'::jsonb,
      operator_code varchar(50) NOT NULL, parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
      on_missing varchar(24) NOT NULL DEFAULT 'unknown', severity varchar(16) NOT NULL DEFAULT 'warning',
      message_template text NOT NULL, remedy_template text,
      primary_source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT, source_excerpt text,
      sort_order integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(matter_version_id, rule_code),
      CONSTRAINT ck_rule_type CHECK (rule_type IN ('completeness','format','consistency','eligibility')),
      CONSTRAINT ck_rule_missing CHECK (on_missing IN ('unknown','missing_material')),
      CONSTRAINT ck_rule_severity CHECK (severity IN ('info','warning','blocking'))
    );
    CREATE INDEX ix_verification_rules_version_order ON verification_rules(matter_version_id, sort_order);

    -- Resident applications and append-only document history.
    CREATE TABLE applications (
      id uuid PRIMARY KEY, application_no varchar(40) NOT NULL UNIQUE,
      owner_user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      status varchar(24) NOT NULL DEFAULT 'draft', scenario_answers jsonb NOT NULL DEFAULT '{}'::jsonb,
      data_origin varchar(16) NOT NULL DEFAULT 'synthetic', content_revision integer NOT NULL DEFAULT 1,
      closed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_application_status CHECK (status IN ('draft','preparing','checking','needs_action','review_pending','prepared','closed','cancelled')),
      CONSTRAINT ck_application_origin CHECK (data_origin IN ('synthetic','authorized_real')),
      CONSTRAINT ck_application_revision CHECK (content_revision > 0),
      CONSTRAINT ck_application_answers CHECK (jsonb_typeof(scenario_answers) = 'object')
    );
    CREATE INDEX ix_applications_owner_created ON applications(owner_user_id, created_at DESC);

    CREATE TABLE application_participants (
      id uuid PRIMARY KEY, application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      participant_code varchar(50) NOT NULL, role_code varchar(32) NOT NULL,
      linked_user_id uuid REFERENCES "user"(id) ON DELETE RESTRICT, display_name varchar(100),
      identity_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(application_id, participant_code),
      CONSTRAINT ck_participant_role CHECK (role_code IN ('applicant','agent','spouse','household_member')),
      CONSTRAINT ck_participant_payload CHECK (jsonb_typeof(identity_payload) = 'object')
    );

    CREATE TABLE application_documents (
      id uuid PRIMARY KEY, application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      material_type_id uuid NOT NULL REFERENCES material_types(id) ON DELETE RESTRICT,
      requirement_id uuid REFERENCES material_requirements(id) ON DELETE RESTRICT,
      participant_id uuid REFERENCES application_participants(id) ON DELETE RESTRICT,
      document_code varchar(80) NOT NULL, classification_status varchar(20) NOT NULL DEFAULT 'unconfirmed',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(application_id, document_code),
      CONSTRAINT ck_document_classification CHECK (classification_status IN ('unconfirmed','confirmed','unsupported'))
    );
    CREATE INDEX ix_application_documents_application ON application_documents(application_id);

    CREATE TABLE document_versions (
      id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES application_documents(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      version_no integer NOT NULL, uploaded_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      status varchar(20) NOT NULL DEFAULT 'active', page_count integer,
      data_origin varchar(16) NOT NULL DEFAULT 'synthetic', created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(document_id, version_no),
      CONSTRAINT ck_document_version_no CHECK (version_no > 0),
      CONSTRAINT ck_document_version_status CHECK (status IN ('active','superseded','withdrawn')),
      CONSTRAINT ck_document_version_pages CHECK (page_count IS NULL OR page_count > 0),
      CONSTRAINT ck_document_version_origin CHECK (data_origin IN ('synthetic','authorized_real'))
    );
    CREATE UNIQUE INDEX uq_document_active_version ON document_versions(document_id) WHERE status = 'active';

    CREATE TABLE document_version_files (
      id uuid PRIMARY KEY, document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT, file_order integer NOT NULL,
      storage_backend varchar(24) NOT NULL DEFAULT 'local', storage_key text NOT NULL,
      original_filename varchar(255) NOT NULL, mime_type varchar(100) NOT NULL, byte_size bigint NOT NULL,
      file_sha256 char(64) NOT NULL, page_count integer, availability varchar(20) NOT NULL DEFAULT 'available',
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(document_version_id, file_order),
      CONSTRAINT ck_file_order CHECK (file_order > 0), CONSTRAINT ck_file_size CHECK (byte_size >= 0),
      CONSTRAINT ck_file_sha256 CHECK (file_sha256 ~ '^[0-9a-fA-F]{64}$'),
      CONSTRAINT ck_file_pages CHECK (page_count IS NULL OR page_count > 0),
      CONSTRAINT ck_file_availability CHECK (availability IN ('available','purge_pending','purged'))
    );

    -- OCR, corrections, reproducible checks and their evidence.
    CREATE TABLE extraction_runs (
      id uuid PRIMARY KEY, document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT, attempt_no integer NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'pending', pipeline_version varchar(100) NOT NULL,
      model_info jsonb NOT NULL DEFAULT '{}'::jsonb, raw_output_storage_key text, error_code varchar(80), error_message text,
      started_at timestamptz, finished_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(document_version_id, attempt_no),
      CONSTRAINT ck_extraction_attempt CHECK (attempt_no > 0),
      CONSTRAINT ck_extraction_status CHECK (status IN ('pending','running','succeeded','failed','cancelled'))
    );

    CREATE TABLE extracted_fields (
      id uuid PRIMARY KEY, extraction_run_id uuid NOT NULL REFERENCES extraction_runs(id) ON DELETE RESTRICT,
      document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
      file_id uuid NOT NULL REFERENCES document_version_files(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      participant_id uuid REFERENCES application_participants(id) ON DELETE RESTRICT,
      field_key varchar(100) NOT NULL, occurrence_no integer NOT NULL DEFAULT 1, raw_text text,
      normalized_value jsonb, value_type varchar(16) NOT NULL DEFAULT 'string', page_number integer NOT NULL,
      bbox jsonb, extraction_method varchar(32) NOT NULL, confidence numeric(5,4),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(extraction_run_id, field_key, occurrence_no),
      CONSTRAINT ck_field_occurrence CHECK (occurrence_no > 0), CONSTRAINT ck_field_type CHECK (value_type IN ('string','date','number','boolean','object','array')),
      CONSTRAINT ck_field_page CHECK (page_number > 0), CONSTRAINT ck_field_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
    );
    CREATE INDEX ix_extracted_fields_application_participant_key ON extracted_fields(application_id, participant_id, field_key);

    CREATE TABLE field_corrections (
      id uuid PRIMARY KEY, field_id uuid NOT NULL REFERENCES extracted_fields(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT, correction_no integer NOT NULL,
      action varchar(16) NOT NULL DEFAULT 'correct', corrected_value jsonb,
      corrected_participant_id uuid REFERENCES application_participants(id) ON DELETE RESTRICT,
      actor_user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT, reason text,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(field_id, correction_no),
      CONSTRAINT ck_correction_no CHECK (correction_no > 0), CONSTRAINT ck_correction_action CHECK (action IN ('confirm','correct'))
    );

    CREATE TABLE check_runs (
      id uuid PRIMARY KEY, application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      run_no integer NOT NULL, input_revision integer NOT NULL, idempotency_key varchar(100) NOT NULL UNIQUE,
      status varchar(20) NOT NULL DEFAULT 'pending', material_summary varchar(24), eligibility_summary varchar(24),
      scenario_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb, config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
      engine_version varchar(100) NOT NULL, model_info jsonb NOT NULL DEFAULT '{}'::jsonb,
      initiated_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      started_at timestamptz, finished_at timestamptz, error_code varchar(80), created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(application_id, run_no), CONSTRAINT ck_check_run_no CHECK (run_no > 0 AND input_revision > 0),
      CONSTRAINT ck_check_run_status CHECK (status IN ('pending','running','succeeded','failed','cancelled')),
      CONSTRAINT ck_material_summary CHECK (material_summary IS NULL OR material_summary IN ('no_issue','issues_found','undetermined')),
      CONSTRAINT ck_eligibility_summary CHECK (eligibility_summary IS NULL OR eligibility_summary IN ('supported','not_supported','undetermined','not_evaluated'))
    );
    CREATE INDEX ix_check_runs_application_run ON check_runs(application_id, run_no DESC);

    CREATE TABLE check_run_documents (
      check_run_id uuid NOT NULL REFERENCES check_runs(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
      PRIMARY KEY(check_run_id, document_version_id)
    );

    CREATE TABLE check_results (
      id uuid PRIMARY KEY, check_run_id uuid NOT NULL REFERENCES check_runs(id) ON DELETE RESTRICT,
      matter_version_id uuid NOT NULL REFERENCES matter_versions(id) ON DELETE RESTRICT,
      rule_id uuid NOT NULL REFERENCES verification_rules(id) ON DELETE RESTRICT,
      result varchar(24) NOT NULL, reason_code varchar(80), reason_text text,
      facts_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb, duration_ms integer,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(check_run_id, rule_id),
      CONSTRAINT ck_check_result CHECK (result IN ('pass','fail','unknown','not_applicable','error')),
      CONSTRAINT ck_check_duration CHECK (duration_ms IS NULL OR duration_ms >= 0)
    );

    CREATE TABLE check_issues (
      id uuid PRIMARY KEY, check_result_id uuid NOT NULL REFERENCES check_results(id) ON DELETE RESTRICT,
      check_run_id uuid NOT NULL REFERENCES check_runs(id) ON DELETE RESTRICT, issue_no integer NOT NULL DEFAULT 1,
      issue_type varchar(32) NOT NULL, severity varchar(16) NOT NULL DEFAULT 'warning', title varchar(200) NOT NULL,
      description text, next_action varchar(24) NOT NULL, remedy_text text, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(check_result_id, issue_no),
      CONSTRAINT ck_issue_no CHECK (issue_no > 0),
      CONSTRAINT ck_issue_type CHECK (issue_type IN ('missing_material','missing_field','conflict','quality','condition','manual_needed','technical')),
      CONSTRAINT ck_issue_severity CHECK (severity IN ('info','warning','blocking')),
      CONSTRAINT ck_issue_action CHECK (next_action IN ('upload','retake','correct','confirm','review','offline','retry'))
    );

    CREATE TABLE issue_evidence (
      id uuid PRIMARY KEY, issue_id uuid NOT NULL REFERENCES check_issues(id) ON DELETE RESTRICT,
      check_run_id uuid NOT NULL REFERENCES check_runs(id) ON DELETE RESTRICT,
      application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      evidence_kind varchar(16) NOT NULL, field_id uuid REFERENCES extracted_fields(id) ON DELETE RESTRICT,
      file_id uuid REFERENCES document_version_files(id) ON DELETE RESTRICT,
      requirement_id uuid REFERENCES material_requirements(id) ON DELETE RESTRICT,
      source_id uuid REFERENCES policy_sources(id) ON DELETE RESTRICT,
      page_number integer, bbox jsonb, quote_text text, sort_order integer NOT NULL DEFAULT 0,
      CONSTRAINT ck_evidence_kind CHECK (evidence_kind IN ('field','file','requirement','source')),
      CONSTRAINT ck_evidence_target CHECK (
        (evidence_kind = 'field' AND field_id IS NOT NULL AND file_id IS NULL AND requirement_id IS NULL AND source_id IS NULL) OR
        (evidence_kind = 'file' AND file_id IS NOT NULL AND field_id IS NULL AND requirement_id IS NULL AND source_id IS NULL) OR
        (evidence_kind = 'requirement' AND requirement_id IS NOT NULL AND field_id IS NULL AND file_id IS NULL AND source_id IS NULL) OR
        (evidence_kind = 'source' AND source_id IS NOT NULL AND field_id IS NULL AND file_id IS NULL AND requirement_id IS NULL)
      )
    );

    CREATE TABLE review_tasks (
      id uuid PRIMARY KEY, application_id uuid NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
      check_run_id uuid NOT NULL REFERENCES check_runs(id) ON DELETE RESTRICT,
      issue_id uuid REFERENCES check_issues(id) ON DELETE RESTRICT, scope varchar(16) NOT NULL DEFAULT 'issue',
      status varchar(24) NOT NULL DEFAULT 'pending', assigned_to uuid REFERENCES "user"(id) ON DELETE RESTRICT,
      requested_by uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT, priority smallint NOT NULL DEFAULT 0,
      request_note text, claimed_at timestamptz, completed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_review_scope CHECK (scope IN ('issue','application')),
      CONSTRAINT ck_review_scope_issue CHECK ((scope = 'issue' AND issue_id IS NOT NULL) OR (scope = 'application' AND issue_id IS NULL)),
      CONSTRAINT ck_review_status CHECK (status IN ('pending','in_progress','waiting_user','completed','cancelled'))
    );
    CREATE INDEX ix_review_tasks_queue ON review_tasks(status, priority DESC, created_at);
    CREATE INDEX ix_review_tasks_assignee ON review_tasks(assigned_to, status, updated_at DESC);

    CREATE TABLE review_records (
      id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES review_tasks(id) ON DELETE RESTRICT,
      record_no integer NOT NULL, actor_user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE RESTRICT,
      outcome varchar(24) NOT NULL, comment text,
      field_correction_id uuid REFERENCES field_corrections(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id, record_no),
      CONSTRAINT ck_review_record_no CHECK (record_no > 0),
      CONSTRAINT ck_review_outcome CHECK (outcome IN ('confirmed','supplement_required','offline_required','system_error','withdrawn'))
    );
    """)


def downgrade() -> None:
    # Historical/precheck records intentionally depend on one another; drop only
    # in a controlled rollback, in exact reverse dependency order.
    op.execute("""
    DROP TABLE review_records;
    DROP TABLE review_tasks;
    DROP TABLE issue_evidence;
    DROP TABLE check_issues;
    DROP TABLE check_results;
    DROP TABLE check_run_documents;
    DROP TABLE check_runs;
    DROP TABLE field_corrections;
    DROP TABLE extracted_fields;
    DROP TABLE extraction_runs;
    DROP TABLE document_version_files;
    DROP INDEX uq_document_active_version;
    DROP TABLE document_versions;
    DROP TABLE application_documents;
    DROP TABLE application_participants;
    DROP TABLE applications;
    DROP TABLE verification_rules;
    DROP TABLE material_acquisition_methods;
    DROP TABLE material_requirements;
    DROP TABLE matter_versions;
    DROP TABLE service_locations;
    DROP TABLE material_types;
    DROP TABLE policy_sources;
    DROP TABLE service_matters;
    """)
