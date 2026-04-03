# ARCHITECTURE — Claims Photo Fraud Detection System

## System Overview

```
                    ┌─────────────┐
                    │   GCS       │
                    │ claim-photos│
                    └──────┬──────┘
                           │ OBJECT_FINALIZE
                    ┌──────▼──────┐
                    │   Pub/Sub   │
                    │ photo-uploads│
                    └──────┬──────┘
                           │ push
                    ┌──────▼──────┐
                    │   Worker    │ Cloud Run (1Gi/2CPU)
                    │  /process   │
                    └──────┬──────┘
                           │ EXIF + Vision + Gemini
                    ┌──────▼──────┐
                    │  Cloud SQL  │ Postgres 17 (ENTERPRISE)
                    │  (results)  │ private network only
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │     API     │          │  Dashboard  │
       │  (FastAPI)  │          │ (React+nginx)│
       │  512Mi/1CPU │          │ 256Mi/1CPU  │
       │ authenticated│          │   public    │
       └─────────────┘          └─────────────┘
```

## Services

| Service | Stack | Cloud Run Name | Port | Auth |
|---------|-------|----------------|------|------|
| API | FastAPI + SQLAlchemy + pg8000 | claims-api | 8080 | JWT (HS256) |
| Worker | Python + Gemini + Vision + exchangelib | claims-worker | 8080 | Pub/Sub push auth |
| Dashboard | React 18 + Vite + nginx | claims-dashboard | 80 | Public (JWT in client) |

## Database (Cloud SQL Postgres 17)

Private network only (no public IP). Connected via VPC connector.

### Tables

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `claims` | contract_id, claim_id (unique), risk_score, red_flags[], gemini_analysis (JSONB), extracted_metadata (JSONB), reverse_image_results (JSONB) | Core fraud results |
| `processed_photos` | storage_key (unique), contract_id, claim_id, status | Idempotency — prevents duplicate processing |
| `users` | username (unique), password_hash, role, is_active | POC auth with bcrypt |
| `system_prompts` | slug (unique), content, model, version, is_active | Configurable Gemini prompts |
| `prompt_history` | prompt_id (FK), version, content, changed_by | Audit trail |
| `golden_dataset` | storage_key, expected_risk_min/max, expected_flags[] | Regression testing baselines |

### Indexes
- `idx_claims_contract` — (contract_id, claim_date DESC) for fast history lookup
- `idx_claims_risk` — (risk_score) WHERE risk_score > 50 for high-risk queries
- `idx_prompts_slug` — (slug) WHERE is_active = true

### Views
- `claims_dashboard_view` — flattens JSONB for analytics (tire/color changes, web match counts)
- `daily_fraud_summary_view` — daily aggregations

### Migrations
Managed via Alembic (`api/alembic/versions/`):
- `001_initial_schema.py` — All tables, indexes, constraints
- `002_add_sql_views.py` — Dashboard and summary views

## Storage (GCS)

```
{project_id}-claim-photos/
  {contract_id}/
    {claim_id}/
      photo_001.jpg
      photo_002.jpg
      ...
```

Bucket config: versioning enabled, 90-day lifecycle to NEARLINE, uniform bucket-level access.

GCS notification on OBJECT_FINALIZE → Pub/Sub topic `photo-uploads`.

## AI Pipeline

### Per-Photo Processing (worker/app/services/)
1. **EXIF extraction** (`exif_service.py`) — camera make/model, GPS (DMS→decimal), timestamps, editing software detection (Photoshop, GIMP, Lightroom, Canva, FaceApp, etc.)
2. **Cloud Vision** (`vision_service.py`) — reverse image search (full/partial/similar matches), web entities, label detection

### Claim-Level Analysis
3. **Gemini** (`gemini_service.py`) — multimodal analysis of all claim photos against contract history (last 10 claims). System prompt loaded from DB (slug: `fraud_system_instruction`). Returns: risk_score, red_flags, tire_brands, vehicle_colors, damage_assessment, geo_timestamp_check, reverse_image_flag, recommendation.
4. **Risk scoring** (`risk_service.py`) — weighted composite: Gemini 50%, web exact matches 20%, partial matches 8%, EXIF anomalies (timestamp 10%, GPS 10%, editing software 8%, missing data 5%). Capped 0-100.
5. **Email alerts** (`email_service.py`) — Exchange EWS for claims scoring >= 80. No-ops gracefully if Exchange not configured.

### Idempotency
Worker checks `processed_photos` table before processing. Duplicate uploads are skipped.

## Infrastructure (Terraform)

All in `terraform/main.tf`:

| Resource | Name | Notes |
|----------|------|-------|
| VPC | claims-vpc | Auto-created subnets |
| Private IP | claims-sql-ip | /16 for Cloud SQL peering |
| VPC Peering | servicenetworking | Cloud SQL private access |
| Cloud SQL | fraud-detection-db | Postgres 17, ENTERPRISE, deletion protection |
| GCS Bucket | {project}-claim-photos | Versioned, lifecycle rules |
| Pub/Sub Topic | photo-uploads | GCS notification source |
| Pub/Sub Sub | worker-photo-sub | Push to worker /process |
| GCS Notification | OBJECT_FINALIZE | → photo-uploads topic |
| Artifact Registry | claims-images | Docker image storage |
| Secret Manager | gemini-api-key, session-secret, exchange-password | Secret values pushed by provision.sh |
| Service Accounts | claims-api, claims-worker | Scoped IAM roles |
| VPC Connector | claims-vpc-connector | Cloud Run → Cloud SQL |

**Not in Terraform**: Cloud Run services (managed by `deploy.sh` to avoid state drift).

### IAM Roles

| Service Account | Roles |
|----------------|-------|
| claims-api | storage.objectAdmin, cloudsql.client, secretmanager.secretAccessor |
| claims-worker | storage.objectViewer, cloudsql.client, secretmanager.secretAccessor |

## Scripts

```
preflight.sh   → Validate environment (auth, .env, tools, GCP, Terraform)
provision.sh   → Enable APIs, Terraform apply, push secret values
deploy.sh      → Build Docker images, deploy Cloud Run, wire Pub/Sub
health_check.sh → Verify services + APIs + infra are alive
teardown.sh    → Destroy everything (handles deletion protection, VPC peering)
seed.py        → Seed users, prompts, test data
```

Flow: `preflight` → `provision` → `deploy` → `health_check`

Teardown: handles Cloud SQL deletion protection (targeted TF apply), force-deletes VPC peering (GCP hold after SQL delete), retries with backoff.

## Auth

- JWT (HS256) with session secret from Secret Manager
- Seeded POC users with bcrypt password hashing
- Roles: admin, reviewer
- Token in `Authorization: Bearer` header
- Dashboard stores token in sessionStorage, auto-redirects to /login on 401

## Testing

- **conftest.py** — In-memory SQLite test DB, FastAPI TestClient, JWT helpers, data factories
- **Auth** — 11 tests (login, logout, /me, expired tokens, bad credentials)
- **Health** — 2 tests (ok, degraded)
- **Prompts** — 14+ tests (CRUD, versioning, categories, duplicates)
- **Claims** — Postgres-only (skipped in SQLite, uses JSONB operators)
- **Golden regression** — Validate scoring against known samples
- **Pipeline E2E** — Full worker flow with mocked external APIs
