-- init_db.sql
-- Claims Photo Fraud Detection System — Full DDL
-- PostgreSQL 17 on Cloud SQL
-- Run once to initialize the database schema.

BEGIN;

-- =============================================================================
-- USERS (POC auth — Section 18A)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,       -- bcrypt
    display_name    VARCHAR(255),
    role            VARCHAR(50) DEFAULT 'reviewer',  -- admin, reviewer
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- CLAIMS (Section 7A)
-- =============================================================================
CREATE TABLE IF NOT EXISTS claims (
    id                      SERIAL PRIMARY KEY,
    contract_id             VARCHAR(100) NOT NULL,
    claim_id                VARCHAR(100) NOT NULL,
    claim_date              DATE,
    reported_loss_date      DATE,
    service_drive_location  TEXT,
    service_drive_coords    VARCHAR(50),       -- "lat,lon"
    photo_uris              TEXT[],             -- array of storage paths
    extracted_metadata      JSONB,              -- full EXIF as JSON
    reverse_image_results   JSONB,              -- Cloud Vision Web Detection
    gemini_analysis         JSONB,              -- full Gemini JSON response
    risk_score              REAL,
    red_flags               TEXT[],             -- array of flag strings
    processed_at            TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(contract_id, claim_id)
);

-- Index for contract-level history lookups
CREATE INDEX IF NOT EXISTS idx_claims_contract ON claims(contract_id, claim_date DESC);

-- Index for high-risk claim filtering
CREATE INDEX IF NOT EXISTS idx_claims_risk ON claims(risk_score DESC) WHERE risk_score > 50;

-- =============================================================================
-- PROCESSED PHOTOS (idempotency tracking — Section 7B)
-- =============================================================================
CREATE TABLE IF NOT EXISTS processed_photos (
    id              SERIAL PRIMARY KEY,
    storage_key     TEXT UNIQUE NOT NULL,    -- full GCS object path
    contract_id     VARCHAR(100),
    claim_id        VARCHAR(100),
    processed_at    TIMESTAMPTZ DEFAULT NOW(),
    status          VARCHAR(20) DEFAULT 'completed'  -- completed, failed, pending
);

-- =============================================================================
-- SYSTEM PROMPTS (Section 13A)
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_prompts (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(100) UNIQUE NOT NULL,  -- machine-readable key
    name            VARCHAR(255) NOT NULL,         -- human-readable label
    category        VARCHAR(50) NOT NULL,          -- 'system_instruction', 'analysis', 'qa', 'notification'
    content         TEXT NOT NULL,                 -- the actual prompt text
    model           VARCHAR(50) DEFAULT 'gemini-2.5-flash',
    is_active       BOOLEAN DEFAULT true,
    version         INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_by      VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_prompts_slug ON system_prompts(slug) WHERE is_active = true;

-- =============================================================================
-- PROMPT HISTORY (audit trail — Section 13E)
-- =============================================================================
CREATE TABLE IF NOT EXISTS prompt_history (
    id          SERIAL PRIMARY KEY,
    prompt_id   INTEGER REFERENCES system_prompts(id),
    version     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    changed_by  VARCHAR(100),
    changed_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- GOLDEN DATASET (baseline heuristics — Section 19D)
-- =============================================================================
CREATE TABLE IF NOT EXISTS golden_dataset (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,        -- e.g. "recycled_stock_photo_001"
    storage_key         TEXT NOT NULL,                 -- GCS object path
    expected_risk_min   REAL NOT NULL,
    expected_risk_max   REAL NOT NULL,
    expected_flags      TEXT[],                        -- flags that MUST appear
    must_not_flags      TEXT[],                        -- flags that must NOT appear
    expected_tire_brand VARCHAR(100),
    expected_color      VARCHAR(100),
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

COMMIT;
