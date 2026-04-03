# ARCHITECTURE — Claims Photo Fraud Detection System

> This document will evolve as the system is built. Currently reflects the planned architecture from the implementation plan.

## System Overview

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

## Services

| Service | Stack | Cloud Run | Port |
|---------|-------|-----------|------|
| API | FastAPI + SQLAlchemy | claims-api | 8080 |
| Worker | Python + Gemini + Vision | claims-worker | 8080 |
| Dashboard | React SPA + nginx | claims-dashboard | 80 |

## Database (Cloud SQL Postgres 17)

### Planned Tables
- `claims` — claim records with risk scores, red flags, status
- `processed_photos` — per-photo results (EXIF, Vision, idempotency)
- `users` — POC auth (seeded users)
- `system_prompts` — configurable Gemini prompts
- `golden_dataset` — known fraud/clean samples for regression

> Exact schemas TBD — will be defined as services are built.

## Storage (GCS)

```
{PROJECT_ID}-claim-photos/
  {contract_id}/
    {claim_id}/
      photo_001.jpg
      photo_002.jpg
      ...
```

## AI Pipeline

1. **EXIF extraction** — camera, GPS, timestamps from photo metadata
2. **Cloud Vision** — reverse image search, label detection
3. **Gemini Enterprise** — multimodal analysis of all claim photos against contract history. Configurable prompts.
4. **Risk scoring** — 0-100 composite score from all signals

## Infrastructure

- Terraform for all GCP resources
- provision.sh — creates everything
- deploy.sh — builds and deploys all Cloud Run services
- seed.py — users, prompts, test data

## What's NOT Built Yet

Everything. This is the plan. Code starts with Phase 1 POC.
