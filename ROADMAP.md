# Roadmap — Claims Photo Fraud Detection System

All section references (e.g. "3C", "9J") map to Implementation Plan 5.

---

## Phase 1: POC (Proof of Concept)

**Goal:** Working end-to-end prototype — demonstrate value, get executive buy-in,
validate core fraud detection capability.

**Timeline:** 3–4 weeks

### Scope

**Infrastructure & Deployment**
- [ ] Full GCP infrastructure via provision.sh → Terraform (10C, 17A)
- [ ] Three Cloud Run services deployed via deploy.sh (9A–9D, 12B, 17B)
- [ ] Cloud SQL connector + SQLAlchemy engine via shared db.py (9J)
- [ ] Env vars + Secret Manager wired in deploy.sh (9G)
- [ ] VPC, IAM, service accounts all created by Terraform (10C–10E)

**Storage & Events**
- [ ] GCS photo storage with correct layout (2A–2C)
- [ ] GCS → Pub/Sub → Worker event trigger (3A–3B)

**Processing Pipeline**
- [ ] Per-photo: EXIF extraction (4) + Cloud Vision reverse image lookup (5)
- [ ] Idempotency via processed_photos table (3D, 7B)
- [ ] Claim-level Gemini analysis with photo aggregation (3C, 6B, 6C)
- [ ] High-risk email alerts via Exchange (21)

**Database**
- [ ] Full Postgres schema: claims, processed_photos (7A–7B)
- [ ] Supporting tables: users (18A), system_prompts (13A), golden_dataset (19D)
- [ ] Claims dashboard + daily fraud summary SQL views (8A, 8C)

**Dashboard & Auth**
- [ ] React SPA: Login, Dashboard, ClaimsList, ClaimDetail pages (15B–15D)
- [ ] JS API client with JWT interceptor (15C)
- [ ] Basic API endpoints: claims list, claims detail, dashboard summary, health (14C, 14D, 14F)
- [ ] Session-based auth with seeded POC users via seed.py (18A–18D)

**Prompt Management & Testing**
- [ ] Prompt CRUD endpoints (13C) + default prompts seeded (13B)
- [ ] Golden dataset validation + basic test suite (19D, 17D)
- [ ] All changes strictly via provision.sh + deploy.sh + seed.py (1B operational mandate)

### Success Criteria

- [ ] Upload 10–20 test photos → full pipeline runs automatically
- [ ] Dashboard shows risk scores, red flags, and contract history
- [ ] High-risk claims trigger email alerts
- [ ] Golden dataset regression passes
- [ ] Exec demo: "Watch Gemini automatically catch a recycled stock photo and a tire-brand swap in real time"

---

## Phase 2: Version 1 (Production-Ready Core)

**Goal:** Hardened, scalable, secure system ready for real claims volume and
claims-team daily use. Missing only nice-to-have polish.

**Timeline:** 4–6 weeks (builds on POC)

### Scope

**Complete API Surface**
- [ ] Photo upload + status endpoints (14B)
- [ ] Photo Q&A — ask Gemini about a specific photo (14B `/ask`)
- [ ] Contract history endpoint (14C)
- [ ] Full dashboard stats endpoint (14D)
- [ ] Remaining SQL views not in POC: contract_history (8B), common queries (8D)

**Monitoring & Logging**
- [ ] Performance metrics table + latency/throughput views (19A–19C)
- [ ] Structured pipeline logging + error notifications (20A–20D)
- [ ] Cloud Logging integration + basic alerting
- [ ] Log retention policies (20E)

**Batch Processing**
- [ ] Batch processing queue for back-testing existing claims (11A–11B)
- [ ] Scaling guidelines documented (11D)

**Dashboard Enhancements**
- [ ] ContractHistory page (15B)
- [ ] PhotoQA page (15B)
- [ ] PromptsManager page — prompt CRUD UI (15B)
- [ ] Prompt versioning + history table (13E)
- [ ] Idle timeout auto-logout (15D)

**Hardening**
- [ ] Health checks passing end-to-end (12C Phase 1, 17C)
- [ ] Idempotency, error handling, and retry logic fully implemented
- [ ] Input validation on all endpoints
- [ ] Auth enforced on all internal endpoints (--no-allow-unauthenticated)
- [ ] Audit and harden secrets rotation via Secret Manager

### Success Criteria

- [ ] Handles 1,000–5,000 real claim photos reliably
- [ ] Claims team uses dashboard daily for high-risk reviews and Q&A
- [ ] All processing is fully scripted and repeatable
- [ ] Cost and performance metrics are tracked and visible
- [ ] System passes internal security and compliance review

---

## Phase 3: Version 1.1 (Full Production + Enterprise Polish)

**Goal:** Complete, polished, enterprise-grade system with all advanced and
future-proof features.

**Timeline:** 2–4 weeks (builds on V1)

### Scope

**External Portal API**
- [ ] Full security layer: API keys, IP allowlists, rate limiting, request logging (16A–16D)
- [ ] Supporting tables: api_keys, api_request_log (16C)
- [ ] Consistent JSON response format (16D)

**Advanced Batch Processing**
- [ ] Vertex AI Batch Inference option for 200K+ photo runs (6D, 11C)
- [ ] Daily/weekly scheduled re-analysis jobs

**Enterprise Features**
- [ ] Data retention & lifecycle policies fully configured (2D)
- [ ] Optional: VPC Service Controls, CMEK encryption
- [ ] Cloud Monitoring dashboards + log-based metrics + automated alerts
- [ ] Golden dataset expanded + nightly regression in CI/CD (19E)
- [ ] Go-live checklist Phases 2–3 complete (12C)

**Documentation & Handover**
- [ ] Complete operational runbook for claims team
- [ ] Cost projections validated against actuals (12D)
- [ ] Architecture diagram finalized and matched to plan sections

**Polish**
- [ ] Dashboard: advanced filtering, export features, UI improvements
- [ ] Any remaining edge cases from Phase 2 feedback

### Success Criteria

- [ ] External claims portal can submit photos programmatically
- [ ] System handles 100K+ photos/month at predictable cost
- [ ] Full auditability, compliance, and scalability
- [ ] Ready for long-term maintenance and future model upgrades

---

## Recommended Execution Order

```
1. provision.sh + deploy.sh + seed.py → POC baseline
2. Implement & test core pipeline (Sections 2–6, 3C aggregation)
3. Build dashboard + auth (Sections 14, 15, 18)
4. Add monitoring, logging, batch (Sections 11, 19, 20)
5. Harden with external API and final polish (Section 16)
```
