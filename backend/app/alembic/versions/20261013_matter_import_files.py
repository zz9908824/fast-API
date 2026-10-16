"""Add uploaded-file and page-block evidence for matter imports."""

from alembic import op


revision = "20261013_matter_import_files"
down_revision = "20261013_matter_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE matter_import_files (
      id uuid PRIMARY KEY,
      job_id uuid NOT NULL REFERENCES matter_import_jobs(id) ON DELETE RESTRICT,
      original_filename varchar(255) NOT NULL, mime_type varchar(100) NOT NULL,
      byte_size bigint NOT NULL, file_sha256 char(64) NOT NULL, storage_key text NOT NULL UNIQUE,
      page_count integer, parse_status varchar(20) NOT NULL DEFAULT 'pending', error_message text,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_matter_import_file_size CHECK (byte_size >= 0),
      CONSTRAINT ck_matter_import_file_sha CHECK (file_sha256 ~ '^[0-9a-fA-F]{64}$'),
      CONSTRAINT ck_matter_import_file_status CHECK (parse_status IN ('pending', 'succeeded', 'failed'))
    );
    CREATE INDEX ix_matter_import_files_job ON matter_import_files(job_id, created_at);
    CREATE TABLE matter_import_document_blocks (
      id uuid PRIMARY KEY,
      file_id uuid NOT NULL REFERENCES matter_import_files(id) ON DELETE RESTRICT,
      block_id varchar(120) NOT NULL, page_number integer, text_content text NOT NULL,
      bbox_json jsonb, ocr_confidence numeric(5,4), extraction_method varchar(40) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ck_matter_import_block_page CHECK (page_number IS NULL OR page_number > 0),
      CONSTRAINT ck_matter_import_block_bbox CHECK (bbox_json IS NULL OR jsonb_typeof(bbox_json) IN ('array', 'object')),
      CONSTRAINT ck_matter_import_block_confidence CHECK (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)),
      UNIQUE(file_id, block_id)
    );
    CREATE INDEX ix_matter_import_blocks_file_page ON matter_import_document_blocks(file_id, page_number);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE matter_import_document_blocks;
    DROP TABLE matter_import_files;
    """)
