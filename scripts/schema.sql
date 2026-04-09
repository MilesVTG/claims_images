-- Schema for Claims Photo Fraud Detection System
-- Source of truth: api/alembic/versions/001_initial_schema.py + 002_add_sql_views.py
-- This file is used by the seed Cloud Run job to create tables if they don't exist.

-- users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'reviewer',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- claims
CREATE TABLE IF NOT EXISTS claims (
    id SERIAL PRIMARY KEY,
    contract_id VARCHAR(100) NOT NULL,
    claim_id VARCHAR(100) NOT NULL,
    claim_date DATE,
    reported_loss_date DATE,
    service_drive_location TEXT,
    service_drive_coords VARCHAR(50),
    photo_uris TEXT[],
    extracted_metadata JSONB,
    reverse_image_results JSONB,
    gemini_analysis JSONB,
    risk_score FLOAT,
    red_flags TEXT[],
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_claims_contract_claim UNIQUE (contract_id, claim_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_contract ON claims (contract_id, claim_date DESC);
CREATE INDEX IF NOT EXISTS idx_claims_risk ON claims (risk_score) WHERE risk_score > 50;

-- processed_photos
CREATE TABLE IF NOT EXISTS processed_photos (
    id SERIAL PRIMARY KEY,
    storage_key TEXT UNIQUE NOT NULL,
    contract_id VARCHAR(100),
    claim_id VARCHAR(100),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'completed'
);

-- system_prompts
CREATE TABLE IF NOT EXISTS system_prompts (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(50) DEFAULT 'gemini-2.5-flash',
    is_active BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_prompts_slug ON system_prompts (slug) WHERE is_active = true;

-- prompt_history
CREATE TABLE IF NOT EXISTS prompt_history (
    id SERIAL PRIMARY KEY,
    prompt_id INTEGER REFERENCES system_prompts(id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    changed_by VARCHAR(100),
    changed_at TIMESTAMPTZ DEFAULT NOW()
);

-- golden_dataset
CREATE TABLE IF NOT EXISTS golden_dataset (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    storage_key TEXT NOT NULL,
    expected_risk_min FLOAT NOT NULL,
    expected_risk_max FLOAT NOT NULL,
    expected_flags TEXT[],
    must_not_flags TEXT[],
    expected_tire_brand VARCHAR(100),
    expected_color VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- test_runs
CREATE TABLE IF NOT EXISTS test_runs (
    id SERIAL PRIMARY KEY,
    run_type VARCHAR(50) NOT NULL DEFAULT 'unit',
    triggered_by VARCHAR(100),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',
    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    duration_ms INTEGER
);

-- test_results
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES test_runs(id) ON DELETE CASCADE,
    test_name VARCHAR(500) NOT NULL,
    test_file VARCHAR(255),
    category VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    duration_ms INTEGER,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results (run_id);

-- Views
CREATE OR REPLACE VIEW claims_dashboard_view AS
SELECT
    c.id,
    c.contract_id,
    c.claim_id,
    c.claim_date,
    c.reported_loss_date,
    c.service_drive_location,
    c.service_drive_coords,
    c.risk_score,
    array_to_string(c.red_flags, ' | ') AS red_flags_list,
    c.gemini_analysis->>'explanation' AS gemini_explanation,
    c.gemini_analysis->>'recommendation' AS recommendation,
    c.gemini_analysis->>'damage_assessment' AS damage_assessment,
    c.gemini_analysis->'tire_brands_detected'->>'current' AS current_tire_brand,
    c.gemini_analysis->'vehicle_colors_detected'->>'current' AS current_vehicle_color,
    (c.gemini_analysis->'tire_brands_detected'->>'current') IS DISTINCT FROM
        (c.gemini_analysis->'tire_brands_detected'->'previous'->>0) AS tire_brand_changed,
    (c.gemini_analysis->'vehicle_colors_detected'->>'current') IS DISTINCT FROM
        (c.gemini_analysis->'vehicle_colors_detected'->'previous'->>0) AS vehicle_color_changed,
    c.gemini_analysis->'geo_timestamp_check'->>'gps_vs_service_drive' AS gps_match_status,
    c.gemini_analysis->'geo_timestamp_check'->>'timestamp_vs_loss_date' AS timestamp_match_status,
    jsonb_array_length(COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)) AS exact_web_matches,
    jsonb_array_length(COALESCE(c.reverse_image_results->'visually_similar_images', '[]'::jsonb)) AS similar_web_images,
    c.reverse_image_results->'pages_with_matching_images'->>0 AS first_matching_page,
    jsonb_array_length(COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)) > 0 AS has_exact_web_match,
    c.extracted_metadata->>'DateTimeOriginal' AS photo_timestamp,
    c.extracted_metadata->>'gps_location' AS photo_gps,
    c.extracted_metadata->>'Make' AS camera_make,
    c.extracted_metadata->>'Model' AS camera_model,
    c.photo_uris[1] AS latest_photo_uri,
    c.processed_at
FROM claims c
ORDER BY c.risk_score DESC NULLS LAST, c.claim_date DESC;

CREATE OR REPLACE VIEW daily_fraud_summary_view AS
SELECT
    DATE(processed_at) AS process_date,
    COUNT(*) AS total_claims_processed,
    COUNT(*) FILTER (WHERE risk_score >= 70) AS high_risk_count,
    COUNT(*) FILTER (WHERE risk_score BETWEEN 40 AND 69) AS medium_risk_count,
    COUNT(*) FILTER (WHERE risk_score < 40) AS low_risk_count,
    ROUND(AVG(risk_score)::numeric, 1) AS avg_risk_score,
    COUNT(*) FILTER (WHERE
        jsonb_array_length(COALESCE(reverse_image_results->'full_matching_images', '[]'::jsonb)) > 0
    ) AS claims_with_web_matches
FROM claims
GROUP BY DATE(processed_at)
ORDER BY process_date DESC;
