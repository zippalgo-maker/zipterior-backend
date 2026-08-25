BEGIN;

CREATE TABLE IF NOT EXISTS bulk_import_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type VARCHAR(40) NOT NULL CHECK (
        job_type IN ('complex_excel', 'company_portfolio_json')
    ),
    status VARCHAR(40) NOT NULL DEFAULT 'uploading' CHECK (
        status IN (
            'uploading', 'awaiting_resolution', 'preview', 'queued',
            'running', 'completed', 'completed_with_errors', 'failed', 'cancelled'
        )
    ),
    original_filename TEXT NOT NULL,
    source_path TEXT,
    expected_size BIGINT NOT NULL CHECK (expected_size > 0),
    uploaded_size BIGINT NOT NULL DEFAULT 0 CHECK (uploaded_size >= 0),
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
    resolved_count INTEGER NOT NULL DEFAULT 0 CHECK (resolved_count >= 0),
    processed_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
    success_count INTEGER NOT NULL DEFAULT 0 CHECK (success_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    skipped_count INTEGER NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    image_success_count INTEGER NOT NULL DEFAULT 0 CHECK (image_success_count >= 0),
    image_failed_count INTEGER NOT NULL DEFAULT 0 CHECK (image_failed_count >= 0),
    error_message TEXT,
    requested_by BIGINT NOT NULL REFERENCES users(id),
    notification_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bulk_import_records (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES bulk_import_jobs(id) ON DELETE CASCADE,
    record_type VARCHAR(30) NOT NULL CHECK (
        record_type IN ('complex', 'company', 'portfolio')
    ),
    record_key VARCHAR(300) NOT NULL,
    source_label TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (
        status IN (
            'pending', 'resolved', 'processing', 'succeeded',
            'duplicate', 'failed', 'skipped'
        )
    ),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_id BIGINT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, record_type, record_key)
);

CREATE TABLE IF NOT EXISTS source_import_links (
    id BIGSERIAL PRIMARY KEY,
    source_system VARCHAR(50) NOT NULL,
    entity_type VARCHAR(30) NOT NULL CHECK (
        entity_type IN ('company', 'portfolio', 'portfolio_image')
    ),
    source_key VARCHAR(300) NOT NULL,
    target_id BIGINT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_system, entity_type, source_key)
);

CREATE INDEX IF NOT EXISTS idx_bulk_import_jobs_status_created
    ON bulk_import_jobs (status, created_at, id);
CREATE INDEX IF NOT EXISTS idx_bulk_import_jobs_requested
    ON bulk_import_jobs (requested_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bulk_import_records_job_status
    ON bulk_import_records (job_id, status, id);
CREATE INDEX IF NOT EXISTS idx_source_import_links_target
    ON source_import_links (entity_type, target_id);

COMMIT;
