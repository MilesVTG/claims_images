# Claims Photo Fraud Detection System

**GCP-native AI-powered fraud detection for insurance claim photos**

Automatically detect recycled stock photos, tire brand changes, vehicle color swaps, staged damage, geo/timestamp mismatches, and other fraud indicators using Gemini Enterprise, Cloud Vision, and EXIF analysis.

---

## Overview

This system ingests claim photos from Google Cloud Storage, runs multimodal AI analysis with Gemini, performs reverse image lookup, extracts EXIF metadata, and surfaces fraud risk scores and red flags through a React dashboard.

Built entirely with GCP-native services (Cloud Run, Cloud SQL Postgres 17, GCS, Pub/Sub, Gemini, Cloud Vision) and designed with a strict **script-first** philosophy — no manual changes to production.

**Key Capabilities**
- Per-photo processing (EXIF extraction + Cloud Vision reverse image search)
- Claim-level Gemini multimodal fraud analysis (aggregates all photos per claim with contract history)
- Composite risk scoring (0-100) with weighted signals and explainable red flags
- React dashboard for claims team review
- High-risk email alerts via Microsoft Exchange
- Configurable Gemini prompts with versioning and audit trail
- Golden dataset for regression testing
- Fully scripted provisioning, deployment, and teardown

---

## Architecture

```
                    ┌─────────────┐
                    │   GCS       │
                    │ claim-photos│
                    └──────┬──────┘
                           │ upload event
                    ┌──────▼──────┐
                    │   Pub/Sub   │
                    └──────┬──────┘
                           │ push
                    ┌──────▼──────┐
                    │   Worker    │ Cloud Run
                    │ (processing)│
                    └──────┬──────┘
                           │ EXIF + Vision + Gemini
                    ┌──────▼──────┐
                    │  Cloud SQL  │ Postgres 17
                    │  (results)  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │     API     │          │  Dashboard  │
       │  (FastAPI)  │          │ (React+nginx)│
       │  Cloud Run  │          │  Cloud Run  │
       └─────────────┘          └─────────────┘
```

1. Photos uploaded to GCS (`{project_id}-claim-photos/{contract_id}/{claim_id}/...`)
2. GCS notification triggers Pub/Sub → pushes to Worker
3. **Per-photo**: EXIF extraction + Cloud Vision reverse image search
4. **Claim-level**: Gemini multimodal analysis against contract history
5. Composite risk score computed (Gemini 50%, web matches 20%, EXIF 30%)
6. Results stored in Cloud SQL Postgres (claims table with JSONB)
7. Claims team reviews via React SPA dashboard
8. High-risk claims (score >= 80) trigger email alerts

---

## Services

| Service | Stack | Cloud Run | Port | Resources |
|---------|-------|-----------|------|-----------|
| API | FastAPI + SQLAlchemy | claims-api | 8080 | 512Mi / 1 CPU |
| Worker | Python + Gemini + Vision | claims-worker | 8080 | 1Gi / 2 CPU |
| Dashboard | React 18 + Vite + nginx | claims-dashboard | 80 | 256Mi / 1 CPU |

### API Endpoints
- `POST /api/auth/login` — JWT authentication
- `GET /api/claims` — List claims with pagination, risk filters, sorting
- `GET /api/claims/{contract_id}/{claim_id}` — Claim detail with photos and history
- `GET /api/dashboard/summary` — KPI aggregates for dashboard
- `GET/POST /api/prompts` — Gemini prompt management with versioning
- `GET /api/health` — Health check with DB connectivity

### Worker Pipeline
- `POST /process` — Pub/Sub push handler (GCS upload events)
- EXIF extraction (camera, GPS, timestamps, editing software detection)
- Cloud Vision (reverse image search, label detection, web entities)
- Gemini multimodal analysis (fraud assessment with all claim photos)
- Composite risk scoring with explainable weights
- Email alerts for high-risk claims via Exchange EWS

### Dashboard Pages
- Login — JWT auth with seeded POC users
- Dashboard — KPI cards, recent high-risk claims
- Claims List — Filterable, sortable table with risk badges
- Claim Detail — Full analysis results, photo gallery, red flags

---

## Database

Cloud SQL Postgres 17 with 6 tables:

| Table | Purpose |
|-------|---------|
| `claims` | Fraud detection results (risk scores, JSONB analysis, red flags) |
| `processed_photos` | Idempotency tracking per photo |
| `users` | POC authentication (seeded users, bcrypt, JWT) |
| `system_prompts` | Configurable Gemini prompts with versioning |
| `prompt_history` | Audit trail for prompt changes |
| `golden_dataset` | Known fraud/clean samples for regression testing |

Plus 2 SQL views: `claims_dashboard_view` and `daily_fraud_summary_view`.

Managed via Alembic migrations (`api/alembic/versions/`).

---

## Infrastructure

All GCP resources managed by Terraform (`terraform/`):

- **Cloud SQL** — Postgres 17, private networking, ENTERPRISE edition
- **VPC** — Private network with peering for Cloud SQL
- **VPC Connector** — Cloud Run → Cloud SQL private access
- **GCS** — Photo storage with versioning, 90-day lifecycle to NEARLINE
- **Pub/Sub** — Topic + push subscription for GCS upload events
- **Artifact Registry** — Docker image storage
- **Secret Manager** — API keys, DB password, session secret, Exchange password
- **Service Accounts** — Scoped IAM (claims-api, claims-worker)
- **Cloud Run** — Deployed via `deploy.sh` (not Terraform, avoids state drift)

---

## Project Structure

```
claims_images/
├── api/                    # FastAPI service
│   ├── app/
│   │   ├── routers/        # auth, claims, dashboard, health, photos, prompts
│   │   ├── models/         # SQLAlchemy ORM (claim, user, prompt, etc.)
│   │   ├── services/       # auth_service
│   │   ├── config.py       # pydantic-settings
│   │   ├── database.py     # Cloud SQL connector + local dev
│   │   └── main.py         # FastAPI app
│   ├── alembic/            # DB migrations
│   ├── Dockerfile
│   └── requirements.txt
├── worker/                 # Processing service
│   ├── app/
│   │   ├── services/       # exif, vision, gemini, risk, email
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py         # Pub/Sub handler
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/              # React SPA
│   ├── src/
│   │   ├── pages/          # Login, Dashboard, ClaimsList, ClaimDetail
│   │   ├── components/     # RiskBadge, PhotoGallery, RedFlagsList, etc.
│   │   └── api/client.js   # API client with JWT
│   ├── Dockerfile
│   └── package.json
├── terraform/              # Infrastructure as Code
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── scripts/
│   ├── preflight.sh        # Pre-run validation
│   ├── provision.sh        # One-time GCP infra setup
│   ├── deploy.sh           # Build + deploy to Cloud Run
│   ├── health_check.sh     # Post-deploy verification
│   ├── teardown.sh         # Destroy all infra (keeps project)
│   ├── seed.py             # Seed users, prompts, test data
│   ├── seed_golden_dataset.py
│   └── upload_test_photos.sh
├── tests/
│   ├── conftest.py         # Fixtures, SQLite test DB, factories
│   ├── test_api_auth.py    # 11 tests
│   ├── test_api_claims.py  # Postgres-only
│   ├── test_api_dashboard.py
│   ├── test_api_health.py  # 2 tests
│   ├── test_api_prompts.py # 14+ tests
│   ├── test_golden_regression.py
│   └── test_pipeline_e2e.py
├── .env                    # Local secrets (gitignored)
├── .gitignore
├── ARCHITECTURE.md
├── INITIAL.md              # Requirements and design decisions
├── ROADMAP.md              # Phased delivery plan
└── README.md
```

---

## Quick Start

### Prerequisites
- `gcloud` CLI authenticated (`gcloud auth login`)
- Application Default Credentials (`gcloud auth application-default login`)
- Project set (`gcloud config set project propane-landing-491118-r7`)
- `.env` file with secrets (see INITIAL.md)
- `terraform`, `docker`, `node`, `python3` installed

### Setup

```bash
# 0. Validate environment
./scripts/preflight.sh

# 1. Provision infrastructure
./scripts/provision.sh

# 2. Deploy all services
./scripts/deploy.sh --all

# 3. Seed users, prompts, and test data
python scripts/seed.py

# 4. Verify everything is healthy
./scripts/health_check.sh

# 5. Upload test photos and watch the pipeline
./scripts/upload_test_photos.sh
```

### Teardown

```bash
./scripts/teardown.sh    # Type 'teardown' to confirm
```

Destroys all infra, keeps the GCP project. Re-provision with `provision.sh`.

---

## GCP Project

| | |
|---|---|
| **Project** | `propane-landing-491118-r7` |
| **Account** | `mchick@vtg-services.net` |
| **Region** | `us-central1` |

---

## Scripts Reference

| Script | Purpose | When to Run |
|--------|---------|-------------|
| `preflight.sh` | Validate env, auth, tools, GCP access | Before provision or deploy |
| `provision.sh` | Enable APIs, Terraform apply, push secrets | First-time setup |
| `deploy.sh` | Build Docker images, deploy to Cloud Run | After code changes |
| `health_check.sh` | Verify services, APIs, infra are alive | After deploy |
| `teardown.sh` | Destroy all infrastructure | Clean slate / cost savings |
| `seed.py` | Seed users, prompts, test data | After first deploy |

All scripts have detailed comment headers with WHAT/WHY/WHEN/IF IT FAILS guidance.

---

## Status

**Phase 1 POC — In Progress**

### Done
- API service (auth, claims, dashboard, prompts, health)
- Worker service (EXIF, Vision, Gemini, risk scoring, email alerts)
- Database schema (6 tables, 2 views, Alembic migrations)
- React dashboard (4 pages, API client with JWT)
- Terraform IaC (all infra defined)
- Scripts (preflight, provision, deploy, health check, teardown)
- Test suite (auth, health, prompts coverage)

### Remaining
- Photo upload API endpoints (`/api/photos` — 4 TODOs)
- Dashboard field mapping fixes
- E2E integration test (full pipeline)
- Golden dataset regression validation
- GCP deploy + smoke test
