# Roadmap

This document tracks major milestones for the GCP-based Claims Image Project.

## Status Legend

| Symbol | Meaning |
|---|---|
| 🔲 | Not Started |
| 🔄 | In Progress |
| ✅ | Complete |
| ⏸ | Blocked / On Hold |

---

## Phase 1 — Planning *(current)*

- 🔄 Define project scope and objectives
- 🔲 Identify stakeholders and data owners
- 🔲 Document data sources and image formats
- 🔲 Define GCP project structure (projects, folders, billing accounts)
- 🔲 Establish IAM roles and access control strategy
- 🔲 Select Vertex AI models / APIs (Vision API vs. AutoML vs. custom)
- 🔲 Define BigQuery dataset schema and retention policies
- 🔲 Draft architecture diagram and get sign-off
- 🔲 Finalize development, staging, and production environment plan

---

## Phase 2 — Infrastructure Setup

- 🔲 Provision GCP project(s) and enable required APIs
- 🔲 Create GCS buckets (raw, processed, archive)
- 🔲 Set up BigQuery datasets and initial table schemas
- 🔲 Configure Pub/Sub topics and subscriptions
- 🔲 Set up service accounts and IAM bindings
- 🔲 Configure Secret Manager for credentials
- 🔲 CI/CD pipeline setup (Cloud Build or GitHub Actions)

---

## Phase 3 — Data Ingestion Pipeline

- 🔲 Build image ingestion workflow (manual upload + event-driven)
- 🔲 Implement Dataflow pipeline for image metadata extraction
- 🔲 Load metadata into BigQuery
- 🔲 Validate end-to-end ingestion with sample data
- 🔲 Implement error handling and dead-letter queues

---

## Phase 4 — Vertex AI Integration

- 🔲 Set up Vertex AI environment and model registry
- 🔲 Prototype image classification / analysis pipeline
- 🔲 Train or fine-tune model on claims image data
- 🔲 Deploy model to Vertex AI endpoint
- 🔲 Integrate prediction results back into BigQuery

---

## Phase 5 — Analytics & Reporting

- 🔲 Build BigQuery views and aggregations for claims insights
- 🔲 Connect Looker Studio (or equivalent) for dashboards
- 🔲 Define KPIs and monitoring metrics
- 🔲 Alerting and anomaly detection setup

---

## Phase 6 — Hardening & Launch

- 🔲 Security review and penetration testing
- 🔲 Performance and load testing
- 🔲 Cost optimization review
- 🔲 Documentation finalized
- 🔲 Production launch
- 🔲 Post-launch monitoring and support plan

---

## Future Considerations

- Multi-region / disaster recovery strategy
- Real-time fraud detection on claims images
- Integration with downstream claims management systems
- Model retraining pipeline (continuous learning)
