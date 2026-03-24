# Claims Photo Fraud Detection System

**GCP-native AI-powered fraud detection for insurance claim photos**

Automatically detect recycled stock photos, tire brand changes, vehicle color swaps, staged damage, geo/timestamp mismatches, and other fraud indicators using Gemini Enterprise, Cloud Vision, and EXIF analysis.

---

## Overview

This system ingests claim photos from Google Cloud Storage, runs multimodal AI analysis with Gemini, performs reverse image lookup, extracts EXIF metadata, and surfaces clear fraud risk scores and red flags through a React dashboard.

Built entirely with GCP-native services (Cloud Run, Cloud SQL Postgres, GCS, Pub/Sub, Gemini, Cloud Vision) and designed with a strict **script-first** philosophy — no manual changes to production.

**Key Capabilities**
- Per-photo processing (EXIF + Cloud Vision)
- Claim-level Gemini fraud analysis (aggregates all photos per claim)
- Risk scoring (0–100) with explainable red flags
- Real-time dashboard for claims team
- High-risk email alerts via Microsoft Exchange
- Golden dataset for regression testing
- Fully scripted provisioning and deployment

---

## Architecture

See **Implementation Plan 5 — Comprehensive** for full details.

High-level flow:
1. Photos uploaded to GCS (`{PROJECT_ID}-claim-photos/{contract_id}/{claim_id}/...`)
2. Pub/Sub triggers worker
3. Per-photo: EXIF extraction + Cloud Vision reverse image lookup
4. Claim-level: Gemini multimodal analysis against contract history
5. Results stored in Cloud SQL Postgres
6. Claims team reviews via React SPA dashboard served by nginx

Core components:
- **Cloud Run Services**: `nginx` (dashboard), `api` (FastAPI), `worker` (processing)
- **Database**: Cloud SQL Postgres 17
- **Storage**: Google Cloud Storage
- **AI**: Gemini Enterprise + Cloud Vision
- **Infra**: Terraform + Bash/Python scripts

---

## Quick Start (POC)

```bash
# 1. Provision infrastructure
./scripts/provision.sh

# 2. Deploy all services
./scripts/deploy.sh --all

# 3. Seed users, prompts, and test data
source .env && python scripts/seed.py

# 4. Run health checks
./scripts/health_check.sh

# 5. Upload test photos and watch the pipeline run
./scripts/upload_test_photos.sh
```

Once deployed:
- **Dashboard URL** → from `gcloud run services describe claims-dashboard`
- Login with seeded users (`miles` / `greg`)
- Upload photos via the dashboard or directly to GCS

---

## Project Structure

```text
claims_images/
├── api/                # FastAPI service
├── worker/             # Background processing service
├── dashboard/          # React SPA + nginx
├── scripts/            # provision.sh, deploy.sh, seed.py, etc.
├── terraform/          # Infrastructure as Code
├── .env                # Local dev secrets (git-ignored)
└── ROADMAP.md
```

Full directory layout and Dockerfiles are detailed in Section 9H of the Implementation Plan.

---

## Roadmap

See **ROADMAP.md** for the three-phase delivery plan:

- **Phase 1: POC** — Working prototype to excite stakeholders (3–4 weeks)
- **Phase 2: Version 1** — Production-ready core system (4–6 weeks)
- **Phase 3: Version 1.1** — Full enterprise features (2–4 weeks)

---

## Key References

- **Implementation Plan 5** — `implementation_plan_5_comprehensive.txt` (the single source of truth)
- **ROADMAP.md** — Phased delivery plan with success criteria
- **Section 1B** — Operational Mandate: Script-first, no hotpatches

> All code changes, infrastructure, and deployments must go through the provided scripts.

---

## Development & Deployment

**Never** run `gcloud run deploy`, manual SQL, or SSH into containers in production.
Use:

- `./scripts/provision.sh` — Terraform + secrets
- `./scripts/deploy.sh [--all | api | worker | dashboard]` — Build & deploy
- `./scripts/seed.py` — Seed users and default prompts
- `./scripts/health_check.sh` — Verify everything is healthy

---

## Documentation

- Full technical specification: `implementation_plan_5_comprehensive.txt`
- Detailed roadmap with checklists: `ROADMAP.md`
- Database schema & SQL views: Sections 7–8
- API endpoints: Section 14
- Dashboard: Section 15
- Processing pipeline: Sections 3–6

---

## Contributing & Maintenance

- All changes must be scripted and version-controlled.
- Update the Implementation Plan first, then the code/scripts.
- Run the full test suite (`scripts/test_suite.py`) and golden dataset regression before any deploy.

---

*Built for insurance fraud detection*
*Questions? Start with the Implementation Plan and ROADMAP.md.*
