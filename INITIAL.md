# INITIAL — Claims Photo Fraud Detection System

## Why We're Building This

Insurance claim photo fraud is manual, slow, and inconsistent. Adjusters review photos by eye and miss patterns — recycled stock images, tire brand swaps between photos, color mismatches, staged damage, geo/timestamp inconsistencies. This system automates detection using multimodal AI so the claims team can focus on the flagged cases instead of reviewing everything.

## Original Requirements

1. **Ingest claim photos** from GCS, process automatically via Pub/Sub trigger
2. **Per-photo analysis** — EXIF metadata extraction + Cloud Vision reverse image search
3. **Claim-level AI analysis** — Gemini aggregates all photos per claim against contract history
4. **Risk scoring** — 0-100 score with explainable red flags
5. **Dashboard** — React SPA for the claims team to review flagged claims
6. **Alerts** — high-risk claims trigger email via Microsoft Exchange
7. **Prompt management** — configurable Gemini prompts, not hardcoded
8. **Golden dataset** — regression testing against known fraud/clean samples

## Constraints

- GCP-native only — Cloud Run, Cloud SQL Postgres, GCS, Pub/Sub, Gemini, Cloud Vision
- Script-first — no manual changes to production. Everything via provision.sh, deploy.sh, seed.py
- Terraform for infrastructure
- POC first — prove value, get exec buy-in, then harden

## Project Phases

- **Phase 1 (POC)**: End-to-end prototype — infra, pipeline, dashboard, auth, prompts. 3-4 weeks.
- **Phase 2 (V1)**: Production hardening — monitoring, batch processing, dashboard enhancements
- **Phase 3 (V1.1)**: Enterprise polish — external API, advanced batch, compliance

## Success Criteria (Phase 1)

- Upload 10-20 test photos → full pipeline runs automatically
- Dashboard shows risk scores, red flags, contract history
- High-risk claims trigger email alerts
- Golden dataset regression passes
- Exec demo: "Watch Gemini catch a recycled stock photo and a tire-brand swap in real time"

## GCP Project Setup

**Project:** `propane-landing-491118-r7` (Claims Photo Analysis)
**Account:** `mchick@vtg-services.net`
**Region:** `us-central1`

### Required GCP APIs

All of these must be enabled for the system to work. Checked/enabled via `scripts/gcp_connect.sh`.

| API | What it's for | Enabled |
|-----|---------------|---------|
| `run.googleapis.com` | Cloud Run — hosts API, Worker, Dashboard services | Yes |
| `sqladmin.googleapis.com` | Cloud SQL Admin — Postgres instance management | Yes |
| `storage.googleapis.com` | Cloud Storage — claim photo storage in GCS | Yes |
| `pubsub.googleapis.com` | Pub/Sub — event-driven photo processing triggers | Yes |
| `aiplatform.googleapis.com` | Vertex AI — Gemini Enterprise multimodal analysis | Yes |
| `vision.googleapis.com` | Cloud Vision — reverse image search, label detection | Yes |
| `cloudbuild.googleapis.com` | Cloud Build — container image builds for Cloud Run | Yes |
| `secretmanager.googleapis.com` | Secret Manager — DB passwords, API keys, secrets | Yes |
| `artifactregistry.googleapis.com` | Artifact Registry — Docker image storage | Yes |

### Local Auth Requirements

- `gcloud auth login` — CLI access to GCP
- `gcloud auth application-default login` — needed for local dev with Python client libraries (ADC)

### First-Time Setup

```bash
gcloud auth login mchick@vtg-services.net
gcloud config set project propane-landing-491118-r7
gcloud config set compute/region us-central1
gcloud auth application-default login
./scripts/gcp_connect.sh   # verifies everything
```

## Design Decisions

- FastAPI for API service (consistent with team experience)
- React SPA served by nginx on Cloud Run (separate from API)
- Background worker as its own Cloud Run service (not async tasks in the API)
- Postgres for structured data, GCS for photos
- Gemini Enterprise for multimodal analysis (not OpenAI — GCP-native constraint)
- Session-based auth with seeded POC users (not OAuth for POC)
