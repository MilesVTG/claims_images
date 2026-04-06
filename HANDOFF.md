# Handoff Notes — Claims Images

Notes for the next conversation. Read this before doing anything.

## TL;DR

POC code is written and working. Infra provision/teardown round trip is verified. Next: provision fresh → deploy → health check → push test photos through the pipeline.

## What To Do First

```bash
./scripts/preflight.sh     # Verify env
./scripts/provision.sh     # Build infra (takes ~7 min, Cloud SQL is slow)
./scripts/deploy.sh --all  # Deploy 3 services to Cloud Run
./scripts/health_check.sh  # Verify everything is alive
```

## What's Left (Jira: POR-5152)

1. **POR-5302** — `/api/photos` endpoints (upload, list, status, ask-question) — the only unbuilt API code
2. **POR-5303** — Dashboard field mapping fixes (submission_date vs processed_at, recent_flagged vs recent_high_risk)
3. **POR-5305** — Deploy to Cloud Run
4. **POR-5306** — E2E integration test
5. **POR-5307** — Golden dataset regression

## Tracking

- **DWB**: Project 5, prefix CI. API at localhost:8000. Use `X-Agent-ID: 1`.
- **Jira**: Project POR, epic POR-5152. CLI: `cd ~/Dev/DWB_2_JIRA && source .venv/bin/activate && dwb2jira ...`
- **Rule**: Real bugs get tickets in both DWB and Jira before fixing. OK to ask if something is worth ticketing.

## Known Gotchas

- `dwb2jira` must run from `~/Dev/DWB_2_JIRA` or it reads the wrong `.env`
- Exchange password has special chars — must be single-quoted in `.env`
- Cloud SQL takes 5min to create, 5min to release VPC peering on delete
- Terraform needs ADC (`gcloud auth application-default login`), not just `gcloud auth login`
- GCP account is `mchick@vtg-services.net` (**.net** not .com)

## Script Colors

All scripts use: cyan banners, orange section headers, red errors, green pass. Defined as vars at top of each script.
