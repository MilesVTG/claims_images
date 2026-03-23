# Claims Image Project

A Google Cloud Platform-based pipeline for processing, analyzing, and managing insurance claims images at scale.

## Overview

This project leverages GCP's Big Data and AI/ML capabilities to ingest, store, process, and extract insights from claims-related images. It is designed to support high-throughput image workflows with automated analysis powered by Vertex AI.

## Tech Stack

| Layer | Technology |
|---|---|
| Image Storage | Google Cloud Storage (GCS) |
| Metadata & Analytics | BigQuery |
| Stream / Batch Ingestion | Pub/Sub + Dataflow |
| AI / ML | Vertex AI (Vision, AutoML, custom models) |
| Orchestration | Cloud Composer (Airflow) |
| Serving / API | Cloud Run |
| Identity & Access | IAM, Secret Manager |

## Architecture

```
Claims Images
     │
     ▼
Cloud Storage (raw)
     │
     ├──► Pub/Sub ──► Dataflow ──► BigQuery (metadata + labels)
     │
     └──► Vertex AI (image analysis / classification)
                │
                ▼
          Results → BigQuery / Cloud Storage (processed)
```

## Getting Started

> Prerequisites and setup instructions will be added as the project progresses through the planning phase.

### Prerequisites

- Google Cloud SDK (`gcloud`) installed and authenticated
- A GCP project with billing enabled
- Required APIs enabled: Cloud Storage, BigQuery, Vertex AI, Pub/Sub, Dataflow

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd claims_images

# Authenticate with GCP
gcloud auth application-default login
gcloud config set project <YOUR_PROJECT_ID>
```

## Project Status

Currently in the **Planning Phase**. See [ROADMAP.md](ROADMAP.md) for milestone tracking.

## Contributing

Contribution guidelines will be defined during the planning phase.

## License

TBD
